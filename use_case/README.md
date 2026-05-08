# Use Case: 批次處理大型 CSV 並行監控

本教學展示如何用 pyrmind 管理多個資料處理程序的執行與監控。

## 情境

你有一個大型 CSV 檔案，需要根據某個欄位（如 category、region、year）分成多個子檔案，
每個子檔案由獨立的處理程序處理。

**範例：** 一個包含 100 萬筆訂單的 CSV，要按地區（region）分成 5 個子檔案，
5 個 Python 程序同時處理各自的 CSV。

## 目錄結構

```
data/
├── orders.csv              # 原始大檔案
└── processed/              # 輸出目錄
    ├── region_asia/
    │   ├── orders.csv      # 亞洲訂單
    │   └── Procfile        # 處理亞洲訂單
    ├── region_europe/
    │   ├── orders.csv
    │   └── Procfile
    ├── region_americas/
    │   ├── orders.csv
    │   └── Procfile
    ├── region_africa/
    │   ├── orders.csv
    │   └── Procfile
    └── region_oceania/
        ├── orders.csv
        └── Procfile
```

## Step 1: 準備處理所需要的腳本

每個處理程序需要一個 Python 腳本。放在 `processor.py`：

```python
#!/usr/bin/env python3
"""CSV 處理程序 - 讀取自己資料夾內的 orders.csv 並處理"""

import csv
import os
import sys
import time
import random

def process_file(input_path, output_path, region):
    """處理 CSV 檔案"""
    processed = 0
    errors = 0
    
    with open(input_path, 'r', encoding='utf-8') as infile:
        reader = csv.DictReader(infile)
        
        with open(output_path, 'w', encoding='utf-8', newline='') as outfile:
            writer = csv.DictWriter(outfile, fieldnames=reader.fieldnames)
            writer.writeheader()
            
            for row in reader:
                # 模擬處理（替換成真實邏輯）
                time.sleep(random.uniform(0.001, 0.01))
                
                # 在這裡做資料處理、清洗、分析等
                processed += 1
                
                if processed % 100 == 0:
                    print(f"[{region}] Processed {processed} rows...")
                
                writer.writerow(row)
    
    return processed, errors

if __name__ == '__main__':
    folder = sys.argv[1] if len(sys.argv) > 1 else '.'
    region = os.path.basename(folder)
    
    input_file = os.path.join(folder, 'orders.csv')
    output_file = os.path.join(folder, 'processed.csv')
    
    print(f"[{region}] Starting processing...")
    print(f"[{region}] Input: {input_file}")
    
    if not os.path.exists(input_file):
        print(f"[{region}] Error: {input_file} not found!")
        sys.exit(1)
    
    processed, errors = process_file(input_file, output_file, region)
    print(f"[{region}] Done! Processed: {processed}, Errors: {errors}")
```

## Step 2: 建立 Procfile 範本

每個資料夾需要一個 `Procfile`：

```procfile
process: python processor.py .
```

## Step 3: 使用 Helper Script 自動分檔並執行

使用 `split_and_run.py` helper script：

```bash
cd use_case
python split_and_run.py
```

Helper 會問你：
1. CSV 檔案路徑
2. 要依據哪個欄位分割
3. 選擇模式：
   - **互動模式**：分完檔後等你檢查，再手動開始執行
   - **直接模式**：分完檔後直接啟動 pyrmind（你可以在另一個 terminal 用 `pyrmind attach` 監控）

## Step 4: 監控進度

在另一個 terminal 執行：

```bash
pyrmind start -f Procfile
```

或使用 helper script 啟動後，在另一個視窗：

```bash
pyrmind attach
```

會看到類似這樣的輸出：

```
┌─────────────────────────────────────────────────────┐
│ Pyrmind Logs (q=quit, j/k=scroll, h/l=switch...) │
│ Processes: 5 | Lines: 234 | Time: 04:15:22          │
│ [region_asia] [region_europe] [region_americas]... │
│─────────────────────────────────────────────────────│
│ [region_asia]     Processing 100 rows...           │
│ [region_europe]   Processing 100 rows...           │
│ [region_americas] Processing 100 rows...           │
│ [region_africa]    Processing 100 rows...           │
│ [region_oceania]  Processing 100 rows...            │
└─────────────────────────────────────────────────────┘
```

## Step 5: 其他管理指令

```bash
# 查看狀態
pyrmind status

# 重啟某個 region 的處理
pyrmind restart region_asia

# 停止某個處理程序
pyrmind stop region_europe

# 全部關閉
pyrmind kill
```

## 完整流程

```
┌──────────────────────────────────────────────────────────────┐
│ Step 1: 準備 orders.csv (百萬筆資料)                          │
└──────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────┐
│ Step 2: python split_and_run.py                              │
│         → 選擇分割欄位 (region)                                │
│         → 選擇模式 (互動/直接)                                 │
│         → 自動分成 5 個資料夾                                 │
└──────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────┐
│ Step 3: pyrmind start -f Procfile                            │
│         (或 helper 直接幫你執行)                              │
└──────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────┐
│ Step 4: pyrmind attach (另一個 terminal)                      │
│         → 監控所有處理進度                                    │
└──────────────────────────────────────────────────────────────┘
```

## 檔案列表

```
use_case/
├── README.md              # 本教學文件
├── split_and_run.py       # Helper script（分割 CSV + 啟動 pyrmind）
├── processor.py           # 處理程序範例
├── Procfile.template      # Procfile 範本
└── sample_data/
    └── orders.csv         # 測試用範例資料
```

## 進階用法

### 指定 base port

如果有多個程式需要不同 port：

```bash
pyrmind start -f Procfile -p 5000
```

### 啟動後動態開關 auto-restart

某個處理程序失敗時不想自動重啟：

```bash
pyrmind autorestart off
```

### 設定 restart cooldown

如果程式需要更長的冷卻時間：

```bash
pyrmind start -f Procfile --restart-cooldown 10.0 --max-restart-count 5
```
