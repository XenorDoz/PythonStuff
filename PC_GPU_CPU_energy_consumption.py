import os
import pandas as pd
import glob
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import time

# Tarifs
PRIX_HP = 0.2146  # € / kWh heures pleines (7h30-23h30)
PRIX_HC = 0.1696  # € / kWh heures creuses (23h30-7h30)

def est_heure_creuse(ts):
    h = ts.time()
    return (h >= time(23,30)) or (h < time(7,30))

# Chargement des fichiers
folder = r"./"
files = glob.glob(os.path.join(folder, "*.csv")) + glob.glob(os.path.join(folder, "*.CSV"))
all_dfs = []

for file in files:
    try:
        df = pd.read_csv(file)
    except Exception as e:
        print(f"Erreur de lecture du fichier {file} : {e}")
        continue

    if 'Date' not in df.columns or 'Time' not in df.columns:
        continue

    df['Timestamp'] = pd.to_datetime(df['Date'].astype(str) + ' ' + df['Time'].astype(str),
                                     dayfirst=True, errors='coerce')

    df['CPU_W'] = pd.to_numeric(df["Consommation d'énergie totale du CPU [W]"], errors='coerce')
    df['GPU_W'] = pd.to_numeric(df["GPU Consommation d'énergie [W]"], errors='coerce')
    df['Total_W'] = df['CPU_W'] + df['GPU_W']

    df = df.dropna(subset=['Timestamp', 'Total_W'])

    all_dfs.append(df[['Timestamp', 'Total_W']])

if not all_dfs:
    print("Aucun fichier valide trouvé. Fin du script.")
    exit()

# Fusion et traitement
df_total = pd.concat(all_dfs).sort_values('Timestamp').reset_index(drop=True)
df_total['Delta'] = df_total['Timestamp'].diff().fillna(pd.Timedelta(seconds=0))
df_total['New_Session'] = df_total['Delta'] > pd.Timedelta(minutes=10)
df_total['Session_ID'] = df_total['New_Session'].cumsum()

# Moyenne par tranche de 30 minutes
sessions = []
for sid, group in df_total.groupby('Session_ID'):
    group = group.set_index('Timestamp')
    group = group.resample('30min').mean(numeric_only=True)
    group['Session_ID'] = sid
    sessions.append(group.reset_index())

df_sessions = pd.concat(sessions)

# Calculs énergie et coût
session_stats = []
for sid, group in df_sessions.groupby('Session_ID'):
    group = group.sort_values('Timestamp')
    duree_h = (group['Timestamp'].iloc[-1] - group['Timestamp'].iloc[0]).total_seconds() / 3600
    puissance_moy = group['Total_W'].mean()
    energie_kwh = puissance_moy * duree_h / 1000

    coût = 0.0
    for _, row in group.iterrows():
        prix = PRIX_HC if est_heure_creuse(row['Timestamp']) else PRIX_HP
        coût += (row['Total_W'] / 1000) * 0.5 * prix  # 0.5h pour 30min

    session_stats.append({
        'Session_ID': sid,
        'Début': group['Timestamp'].iloc[0],
        'Fin': group['Timestamp'].iloc[-1],
        'Durée_h': duree_h,
        'Puissance_moy_W': puissance_moy,
        'Énergie_kWh': energie_kwh,
        'Coût_€': coût
    })

# Affichage console
print("\nConsommation et coût par session :")
for s in session_stats:
    print(f"Session {s['Session_ID']} | Début: {s['Début']} | Durée: {s['Durée_h']:.2f} h | "
          f"Énergie: {s['Énergie_kWh']:.3f} kWh | Coût: {s['Coût_€']:.3f} €")

# Affichage graphique sans décalage vertical
plt.figure(figsize=(14,7))
for sid in df_sessions['Session_ID'].unique():
    group = df_sessions[df_sessions['Session_ID'] == sid]
    plt.plot(group['Timestamp'], group['Total_W'], label=f'Session {sid}')

plt.xlabel("Temps")
plt.ylabel("Consommation totale (W)")
plt.title("Consommation CPU+GPU par session (moyenne toutes les 30 min)")
plt.legend()
plt.grid(True)
plt.gca().xaxis.set_major_locator(mdates.AutoDateLocator())
plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%d-%m %H:%M'))
plt.xticks(rotation=45)
plt.tight_layout()
plt.show()
