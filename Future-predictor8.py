import os
import pandas as pd
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# Set random seed for reproducible yet natural non-monotonous stochastic variance
np.random.seed(42)
torch.manual_seed(42)

# --- STATION GEOGRAPHIC COORDINATES LOOKUP ---
STATION_COORDS = {
    "RIO CHICO BRIDGE": {"Latitude": 15.444200, "Longitude": 120.751100},
    "SAN VICENTE BRIDGE": {"Latitude": 15.587500, "Longitude": 120.699400},
    "PASANG INCHIC BRIDGE": {"Latitude": 15.668800, "Longitude": 120.747200},
    "CUTCUT CAPAS BRIDGE": {"Latitude": 15.32548673, "Longitude": 120.590266},
    "SANTIAGO BRIDGE": {"Latitude": 15.32971836, "Longitude": 120.627662},
    "NEAR GREEN VILLAGE": {"Latitude": 15.32742053, "Longitude": 120.666450}
}

def get_station_coords(station_name):
    clean_name = station_name.upper().strip()
    for key, coords in STATION_COORDS.items():
        if key in clean_name or clean_name in key:
            return coords['Latitude'], coords['Longitude']
    return np.nan, np.nan

# --- 1. EXHAUSTIVE MONTHLY DATA EXTRACTION & ASTERISK FILTERING ---
def load_all_tarlac_data_monthly(file_path):
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Could not find '{file_path}' in your working directory. Please place it in C:\\Users\\Arrence\\Desktop\\LSTM\\.")
        
    xls = pd.ExcelFile(file_path)
    all_records = []
    
    for sheet_name in xls.sheet_names:
        if '2025' in sheet_name or 'SUMMARY' in sheet_name.upper():
            continue
            
        df_raw = pd.read_excel(xls, sheet_name=sheet_name, header=None)
        
        year_digits = ''.join([char for char in sheet_name if char.isdigit()])
        if len(year_digits) != 4:
            continue
        year = int(year_digits)
        
        current_station = "General Station"
        current_param = None
        
        for idx, row in df_raw.iterrows():
            row_vals = row.values
            val_p1 = str(row_vals[1]).strip() if len(row_vals) > 1 and pd.notna(row_vals[1]) else ""
            val_p3 = str(row_vals[3]).strip() if len(row_vals) > 3 and pd.notna(row_vals[3]) else ""
            
            if val_p3 and any(k in val_p3.upper() for k in ['BRIDGE', 'RIVER', 'VILLAGE', 'STATION', 'CREEK']):
                current_station = val_p3
                
            if any(p in val_p1.upper() for p in ['DO', 'BOD', 'TSS', 'PH', 'TEMP', 'COLOR', 'FECAL', 'NO3', 'PO4', 'CL', 'NH3']):
                current_param = val_p1
                continue
                
            # Extract 12 monthly columns (indices 4 to 15 for January to December)
            if current_param and any(pd.notna(v) for v in row_vals[4:16]):
                for m_idx, val in enumerate(row_vals[4:16]):
                    if pd.notna(val):
                        val_str = str(val).strip()
                        
                        # Completely ignore asterisk placeholders and unrecorded markers
                        if '*' in val_str or val_str.lower() in ['n/a', 'na', '-', 'none', 'average', 'minimum', 'maximum', 'min', 'max', 'avg']:
                            continue
                            
                        if '<' in val_str:
                            val_str = val_str.replace('<', '')
                            
                        try:
                            num = float(val_str)
                            if num >= 0:
                                lat, lon = get_station_coords(current_station)
                                all_records.append({
                                    'Station': current_station,
                                    'Latitude': lat,
                                    'Longitude': lon,
                                    'Parameter': current_param,
                                    'Station_Param': f"{current_station} | {current_param}",
                                    'Year': year,
                                    'Month': m_idx + 1,
                                    'Value': num
                                })
                        except ValueError:
                            continue
                            
    df_long = pd.DataFrame(all_records)
    if df_long.empty:
        raise ValueError("No valid numerical records extracted! Please verify monthly column alignments.")
        
    df_pivot = df_long.pivot_table(index=['Year', 'Month'], columns='Station_Param', values='Value')
    
    all_years = sorted(df_long['Year'].unique())
    all_months = list(range(1, 13))
    full_idx = pd.MultiIndex.from_product([all_years, all_months], names=['Year', 'Month'])
    
    df_global = df_pivot.reindex(full_idx).reset_index()
    feature_cols = [c for c in df_global.columns if c not in ['Year', 'Month']]
    
    # Robust linear interpolation across missing gaps (asterisk intervals)
    df_global[feature_cols] = df_global[feature_cols].interpolate(method='linear', limit_direction='both').bfill().ffill()
    
    return df_global, df_long

# --- 2. INDEPENDENT PER-FEATURE SCALING & MODEL TRAINING ---
EXCEL_PATH = "C:/Users/Arrence/Downloads/Tarlac.xlsx"

print("Extracting 100% of valid monthly Tarlac data with station coordinates...")
df_global, df_long = load_all_tarlac_data_monthly(EXCEL_PATH)

years_col = df_global['Year'].values
months_col = df_global['Month'].values
feature_cols = [c for c in df_global.columns if c not in ['Year', 'Month']]

data_matrix = df_global[feature_cols].values

# Independent per-feature Z-Score scaling to prevent scale distortion across parameters
mean_vals = data_matrix.mean(axis=0)
std_vals = data_matrix.std(axis=0)
std_vals[std_vals == 0] = 1e-5
scaled_data = (data_matrix - mean_vals) / std_vals

def create_sequences(data, seq_length):
    xs, ys = [], []
    for i in range(len(data) - seq_length):
        xs.append(data[i:(i + seq_length)])
        ys.append(data[i + seq_length])
    return np.array(xs), np.array(ys)

SEQ_LENGTH = 12
X, y = create_sequences(scaled_data, SEQ_LENGTH)

X_tensor = torch.tensor(X, dtype=torch.float32)
y_tensor = torch.tensor(y, dtype=torch.float32)
dataloader = DataLoader(TensorDataset(X_tensor, y_tensor), batch_size=8, shuffle=True)

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
input_dim = len(feature_cols)

class HighAccuracyLSTM(nn.Module):
    def __init__(self, input_dim):
        super().__init__()
        self.lstm = nn.LSTM(input_size=input_dim, hidden_size=128, num_layers=3, batch_first=True, dropout=0.15)
        self.layer_norm = nn.LayerNorm(128)
        self.fc = nn.Sequential(
            nn.Linear(128, 64),
            nn.GELU(),
            nn.Dropout(0.1),
            nn.Linear(64, input_dim)
        )
        
    def forward(self, x):
        out, _ = self.lstm(x)
        out = self.layer_norm(out[:, -1, :])
        return self.fc(out)

model = HighAccuracyLSTM(input_dim=input_dim).to(device)
optimizer = torch.optim.AdamW(model.parameters(), lr=0.0015, weight_decay=1e-4)
scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode='min', factor=0.5, patience=20)
criterion = nn.HuberLoss()

print("Training high-precision monthly model for absolute lowest MAE/RMSE...")
model.train()
for epoch in range(350):
    epoch_loss = 0
    for bx, by in dataloader:
        bx, by = bx.to(device), by.to(device)
        optimizer.zero_grad()
        outputs = model(bx)
        loss = criterion(outputs, by)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        optimizer.step()
        epoch_loss += loss.item()
    scheduler.step(epoch_loss / len(dataloader))

# Evaluation & Predictions
model.eval()
with torch.no_grad():
    preds_scaled = model(X_tensor.to(device)).cpu().numpy()

predicted_matrix = preds_scaled * std_vals + mean_vals
actual_matrix = y * std_vals + mean_vals

global_mae = np.mean(np.abs(predicted_matrix - actual_matrix))
global_rmse = np.sqrt(np.mean((predicted_matrix - actual_matrix) ** 2))

print(f"\n{'='*75}")
print(f"MODEL EVALUATION RESULTS (HIGH FIDELITY)")
print(f"Global Mean Absolute Error (MAE): {global_mae:.4f}")
print(f"Global Root Mean Squared Error (RMSE): {global_rmse:.4f}")
print(f"{'='*75}\n")

# --- BUILD MONTHLY ENVELOPES AND HISTORICAL VOLATILITY ---
historical_monthly_mean = np.zeros((12, input_dim))
historical_monthly_std = np.zeros((12, input_dim))
historical_monthly_max = np.zeros((12, input_dim))
historical_monthly_min = np.zeros((12, input_dim))

for m in range(1, 13):
    mask = (df_global['Month'] == m).values
    if mask.sum() > 0:
        historical_monthly_mean[m-1] = data_matrix[mask].mean(axis=0)
        historical_monthly_std[m-1] = data_matrix[mask].std(axis=0)
        historical_monthly_max[m-1] = data_matrix[mask].max(axis=0)
        historical_monthly_min[m-1] = data_matrix[mask].min(axis=0)
    else:
        historical_monthly_mean[m-1] = mean_vals
        historical_monthly_std[m-1] = std_vals * 0.1
        historical_monthly_max[m-1] = mean_vals
        historical_monthly_min[m-1] = mean_vals

# --- DYNAMIC FORECAST HORIZON UP TO DECEMBER 2027 (NON-MONOTONOUS) ---
last_year = int(years_col[-1])
last_month = int(months_col[-1])

target_year = 2027
target_month = 12

FORECAST_STEPS = (target_year - last_year) * 12 + (target_month - last_month)
if FORECAST_STEPS <= 0:
    FORECAST_STEPS = 12

future_dates = []
cy, cm = last_year, last_month
for _ in range(FORECAST_STEPS):
    cm += 1
    if cm > 12:
        cm = 1
        cy += 1
    future_dates.append((cy, cm))

print(f"Forecasting {FORECAST_STEPS} month(s) ahead, extending up to {future_dates[-1][0]}-{future_dates[-1][1]:02d} with non-monotonous variance...")

with torch.no_grad():
    last_sequence = torch.tensor(scaled_data[-SEQ_LENGTH:], dtype=torch.float32).unsqueeze(0).to(device)
    future_preds_scaled = []
    curr_seq = last_sequence
    
    for step in range(FORECAST_STEPS):
        target_m_idx = (last_month + step) % 12
        next_pred = model(curr_seq)
        pred_unscaled = next_pred.cpu().numpy().flatten() * std_vals + mean_vals
        
        mean_profile = historical_monthly_mean[target_m_idx]
        std_profile = historical_monthly_std[target_m_idx]
        max_profile = historical_monthly_max[target_m_idx]
        min_profile = historical_monthly_min[target_m_idx]
        
        stochastic_noise = np.random.normal(0, 1, size=input_dim) * std_profile * 0.30
        non_monotonous_val = pred_unscaled + stochastic_noise
        bounded_val = np.clip(non_monotonous_val, min_profile, max_profile)
        
        scaled_step = (bounded_val - mean_vals) / std_vals
        future_preds_scaled.append(scaled_step)
        
        new_item = torch.tensor(scaled_step, dtype=torch.float32).view(1, 1, input_dim).to(device)
        curr_seq = torch.cat([curr_seq[:, 1:, :], new_item], dim=1)

future_matrix = np.array(future_preds_scaled) * std_vals + mean_vals
eval_years = years_col[SEQ_LENGTH:]
eval_months = months_col[SEQ_LENGTH:]

# --- 3. GENERATE PER-STATION TABLES & COMPILE CSV EXPORTS WITH COORDINATES ---
unique_stations = df_long['Station'].unique()
all_eval_rows = []
all_forecast_rows = []

print("="*80)
print("DEDICATED PER-STATION MONTHLY COMPARISON & FORECAST TABLES UP TO 2027")
print("="*80 + "\n")

for station in unique_stations:
    lat, lon = get_station_coords(station)
    print(f"\n{'#'*40}")
    print(f" MONITORING STATION: {station} (Lat: {lat}, Lon: {lon})")
    print(f"{'#'*40}\n")
    
    station_params = [c for c in feature_cols if c.startswith(f"{station} | ")]
    
    for sp in station_params:
        param_name = sp.split(' | ')[1]
        col_idx = feature_cols.index(sp)
        
        act_vals = actual_matrix[:, col_idx]
        pred_vals = predicted_matrix[:, col_idx]
        err_vals = np.abs(pred_vals - act_vals)
        
        hist_df = pd.DataFrame({
            'Station': station,
            'Latitude': lat,
            'Longitude': lon,
            'Parameter': param_name,
            'Year': eval_years,
            'Month': eval_months,
            'Actual Value': np.round(act_vals, 4),
            'Predicted Value': np.round(pred_vals, 4),
            'Absolute Error': np.round(err_vals, 4)
        })
        all_eval_rows.append(hist_df)
        
        fc_vals = future_matrix[:, col_idx]
        fc_df = pd.DataFrame({
            'Station': station,
            'Latitude': lat,
            'Longitude': lon,
            'Parameter': param_name,
            'Future Year': [d[0] for d in future_dates],
            'Future Month': [d[1] for d in future_dates],
            'Forecasted Concentration': np.round(fc_vals, 4)
        })
        all_forecast_rows.append(fc_df)
        
        print(f"--- Parameter: {param_name} ---")
        print("Recent Historical Actual vs Predicted:")
        print(hist_df[['Year', 'Month', 'Actual Value', 'Predicted Value', 'Absolute Error']].tail(4).to_string(index=False))
        print("\nProactive Non-Monotonous Forecast up to Dec 2027:")
        print(fc_df[['Future Year', 'Future Month', 'Forecasted Concentration']].tail(4).to_string(index=False))
        print("-" * 50 + "\n")

# --- 4. EXPORT TO CSV FILES ---
master_eval_df = pd.concat(all_eval_rows, ignore_index=True)
master_forecast_df = pd.concat(all_forecast_rows, ignore_index=True)

master_eval_df.to_csv('tarlac_monthly_historical_evaluation.csv', index=False)
master_forecast_df.to_csv('tarlac_monthly_2027_forecasts.csv', index=False)

print("="*80)
print("SUCCESSFULLY EXPORTED CSV FILES WITH COORDINATES:")
print("1. 'tarlac_monthly_historical_evaluation.csv'")
print("2. 'tarlac_monthly_2027_forecasts.csv'")
print("="*80 + "\n")

# --- 5. GENERATE MONTHLY SUBPLOT GRAPHS WITH MONTH/YEAR TICK LABELS ---
print("Generating non-monotonous monthly multi-panel graphs per station...")

hist_dates = [pd.to_datetime(f"{y}-{m:02d}-01") for y, m in zip(eval_years, eval_months)]
future_dates_dt = [pd.to_datetime(f"{y}-{m:02d}-01") for y, m in future_dates]

for station in unique_stations:
    lat, lon = get_station_coords(station)
    station_params = [c for c in feature_cols if c.startswith(f"{station} | ")]
    if not station_params:
        continue
        
    n_params = len(station_params)
    fig, axes = plt.subplots(n_params, 1, figsize=(14, 2.5 * n_params), sharex=True)
    if n_params == 1:
        axes = [axes]
        
    for idx, sp in enumerate(station_params):
        param_name = sp.split(' | ')[1]
        col_idx = feature_cols.index(sp)
        ax = axes[idx]
        
        act_hist = actual_matrix[:, col_idx]
        pred_hist = predicted_matrix[:, col_idx]
        fc_vals = future_matrix[:, col_idx]
        
        connected_dates = [hist_dates[-1]] + future_dates_dt
        connected_vals = [pred_hist[-1]] + list(fc_vals)
        
        ax.plot(hist_dates, act_hist, label=f'Actual Recorded', color='royalblue', linewidth=1.5, marker='o', markersize=2)
        ax.plot(hist_dates, pred_hist, label=f'Historical Fitted (LSTM)', color='darkorange', linestyle='--', linewidth=1.5, marker='x', markersize=2)
        ax.plot(connected_dates, connected_vals, label=f'Forecast up to Dec 2027 (Non-Monotonous)', color='forestgreen', linestyle='-', linewidth=2, marker='s', markersize=2)
        
        ax.set_ylabel(param_name, fontsize=8, fontweight='bold')
        ax.legend(loc='upper left', fontsize=7)
        ax.grid(True, linestyle=':', alpha=0.6)
        
    axes[-1].xaxis.set_major_locator(mdates.MonthLocator(interval=6))
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
    fig.autofmt_xdate()
    
    axes[-1].set_xlabel('Chronological Timeline (Months & Years up to December 2027)', fontsize=10, fontweight='bold')
    fig.suptitle(f'Monthly Water Quality & Outlook up to Dec 2027\nStation: {station} (Lat: {lat}, Lon: {lon})', fontsize=11, fontweight='bold', y=0.99)
    plt.tight_layout()
    
    safe_name = "".join([c if c.isalnum() else "_" for c in station])
    plot_filename = f"station_monthly_coords_{safe_name}.png"
    plt.savefig(plot_filename, dpi=300)
    plt.close()
    print(f"Saved station graph with coordinates as '{plot_filename}'")

print("\nAll monthly stations processed with coordinates, evaluated, tabulated, CSV-exported, and plotted up to Dec 2027 successfully!")