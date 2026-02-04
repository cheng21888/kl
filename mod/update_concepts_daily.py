# -*- coding: utf-8 -*-
"""
合并脚本：同花顺数据自动下载与所属概念更新
适用环境：GitHub Actions / 本地自动化任务
优化：仅保存必要列，大幅减少CSV体积
"""

import os
import sys
import time
import random
import glob
import re
import pandas as pd
import pywencai
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

# =====================================================================
# --- 0. 全局路径与环境配置 ---
# =====================================================================

from modules.config import CONCEPT_PATH, CALENDAR_PATH, DOWNLOAD_CONFIGS,THS_DATA_ROOT
# =====================================================================
# --- I. 下载配置部分 (新增 keep_cols) ---
# =====================================================================
# 注意：pywencai 返回的列名可能包含 "code", "股票代码", "股票名称" 等
DOWNLOAD_CONFIGS = {
    '收盘数据': {
        'backup_dir': os.path.join(THS_DATA_ROOT, '收盘'),
        'max_threads': 2,
        'question_suffix': '所属行业',  # 只需要行业，问句简化
        'data_threshold': 3000, 
        'query_delay_range': (3, 6),
        # 只保留代码、名称和行业
        'keep_cols': ['股票代码', 'code', '股票名称', '所属同花顺行业']
    },
    '涨跌停数据': {
        'backup_dir': os.path.join(THS_DATA_ROOT, '涨停'),
        'max_threads': 4,
        'question_suffix': '涨跌停',
        'data_threshold': 0, 
        'query_delay_range': (3, 6),
        # 只保留代码、名称和原因
        'keep_cols': ['股票代码', 'code', '股票名称', '涨停原因类别']
    },
    '所属概念': {
        'backup_dir': os.path.join(THS_DATA_ROOT, '所属概念'),
        'max_threads': 2,
        'question_suffix': '所属概念',
        'data_threshold': 3000,
        'query_delay_range': (3, 6),
        # 只保留代码、名称和概念
        'keep_cols': ['股票代码', 'code', '股票名称', '所属概念']
    }
}

SCENARIO_ORDER = ['收盘数据', '涨跌停数据', '所属概念']

# =====================================================================
# --- II. 核心工具函数 ---
# =====================================================================

def get_beijing_now():
    utc_now = datetime.utcnow()
    return utc_now + timedelta(hours=8)

def get_closest_trade_date():
    print(f"📅 正在计算目标交易日...")
    if not os.path.exists(CALENDAR_PATH):
        print(f"❌ 错误：交易日历文件未找到: {CALENDAR_PATH}")
        return None
    try:
        jyrl = pd.read_csv(CALENDAR_PATH)
        if 'date' not in jyrl.columns:
             jyrl['date'] = pd.to_datetime(jyrl['trade_date']).dt.date
    except Exception as e:
        print(f"❌ 读取交易日历失败: {e}")
        return None

    now_date = get_beijing_now().date()
    filtered_trades = jyrl[jyrl['date'] <= now_date].sort_values(by='date', ascending=False)
    
    if filtered_trades.empty:
        return None
    
    target_date_str = filtered_trades.iloc[0]['trade_date']
    print(f"✅ 选定处理日期: {target_date_str}")
    return target_date_str

def format_code(code):
    if pd.isna(code): return ""
    s = str(code)
    res = re.findall(r'\d+', s)
    return res[0].zfill(6) if res else ""

def clean_old_files(backup_dir, keep_days=30):
    if not os.path.exists(backup_dir): return
    files = glob.glob(os.path.join(backup_dir, "*.csv"))
    files.sort(reverse=True) 
    if len(files) > keep_days:
        print(f"🧹 清理 {os.path.basename(backup_dir)}: 保留最新 {keep_days} 个")
        for f in files[keep_days:]:
            try: os.remove(f)
            except: pass

# =====================================================================
# --- III. 下载逻辑 (优化：列过滤) ---
# =====================================================================

def download_task(date, config_name, config):
    max_retries = 3 
    backup_dir = config['backup_dir']
    question_suffix = config['question_suffix']
    data_threshold = config['data_threshold']
    keep_cols = config.get('keep_cols', [])
    
    os.makedirs(backup_dir, exist_ok=True)
    date_chinese = f"{date[:4]}年{int(date[5:7])}月{int(date[8:10])}日"
    question = f'{date_chinese}{question_suffix}'
    save_path = os.path.join(backup_dir, f'{date}.csv')
    
    for retry in range(max_retries):
        try:
            time.sleep(random.uniform(*config['query_delay_range']))
            res = pywencai.get(question=question, loop=True)

            if res is None:
                print(f"  ⚠️ [{config_name}] 返回空，重试 {retry+1}")
                continue

            if len(res) < data_threshold:
                print(f"  ⚠️ [{config_name}] 数据少 ({len(res)})，重试 {retry+1}")
                continue

            # --- 关键修改：只保留需要的列 ---
            if keep_cols:
                # 找出 DataFrame 中存在的、且在保留列表中的列
                existing_cols = [c for c in keep_cols if c in res.columns]
                
                # 有时候 pywencai 返回的列名会有细微差别（比如"涨停原因类别"变成"涨停原因类别[20250101]"）
                # 这里做一个模糊匹配补充
                for col in res.columns:
                    for target in keep_cols:
                        if target in col and col not in existing_cols:
                            # 避免把 unrelated column 比如 '股票代码.1' 加进来
                            if len(col) < len(target) + 15: 
                                existing_cols.append(col)
                
                # 去重
                existing_cols = list(set(existing_cols))
                
                if existing_cols:
                    res = res[existing_cols]

            # 保存
            res.to_csv(save_path, index=False, encoding='utf-8-sig')
            print(f"  ✅ [{config_name}] 下载成功: {len(res)} 条")
            clean_old_files(backup_dir)
            return True

        except Exception as e:
            print(f"  ❌ [{config_name}] 异常: {str(e)[:50]}")
            time.sleep(5) 

    return False

def run_downloads(target_date):
    print(f"\n🚀 [第一步] 下载数据 ({target_date})...")
    success_count = 0
    with ThreadPoolExecutor(max_workers=1) as executor:
        futures = {}
        for name in SCENARIO_ORDER:
            config = DOWNLOAD_CONFIGS[name]
            futures[executor.submit(download_task, target_date, name, config)] = name
        for future in futures:
            if future.result(): success_count += 1
    return success_count > 0 

# =====================================================================
# --- IV. 数据合成逻辑 ---
# =====================================================================

def process_and_merge_files():
    print(f"\n🚀 [第二步] 合成 [所属概念.csv]...")
    daily_dir = DOWNLOAD_CONFIGS['所属概念']['backup_dir']
    closing_dir = DOWNLOAD_CONFIGS['收盘数据']['backup_dir']
    zt_dir = DOWNLOAD_CONFIGS['涨跌停数据']['backup_dir']

    # --- 1. 概念 ---
    # --- 1. 概念 ---
    c_list = []
    if os.path.exists(daily_dir):
        files = sorted(glob.glob(os.path.join(daily_dir, "*.csv")), reverse=True)[:10]
        for f in files:
            try:
                # 1. 读取数据
                try: df = pd.read_csv(f, encoding='gbk', dtype=str)
                except: df = pd.read_csv(f, encoding='utf-8-sig', dtype=str)
                
                # 2. 统一“股票代码”列名
                # 自动寻找包含'代码'字样的列，或者直接指定
                if '代码' in df.columns and '股票代码' not in df.columns:
                    df.rename(columns={'代码': '股票代码'}, inplace=True)
                
                # 3. 处理“股票简称” (如果不存在则填空，防止报错)
                if '股票简称' not in df.columns and '股票名称' not in df.columns:
                    df['股票简称'] = '' # 或者根据业务逻辑去其他文件找简称
                elif '股票名称' in df.columns:
                    df.rename(columns={'股票名称': '股票简称'}, inplace=True)
    
    # --- 关键修改点 3: 精确匹配“所属概念” ---
                # 排除掉“所属概念数量”，只找名字完全等于“所属概念”的列
                concept_col = next((c for c in df.columns if c == '所属概念'), None)
                
                if concept_col and '股票代码' in df.columns:
                    # 标准化列名
                    df.rename(columns={concept_col: '所属概念'}, inplace=True)
                    df['股票代码'] = df['股票代码'].apply(format_code)
                    df['file_date'] = os.path.basename(f)[:10]
                    
                    # 只选取存在的列，避免 KeyError
                    available_cols = [c for c in ['股票代码', '股票简称', '所属概念', 'file_date'] if c in df.columns]
                    c_list.append(df[available_cols])
                    
            except Exception as e:
                print(f"⚠️ 处理文件 {os.path.basename(f)} 时出错: {e}") # 建议打印错误，方便调试
                pass

    df_c = pd.concat(c_list, ignore_index=True)
    df_c = df_c.sort_values(by=['股票代码', 'file_date'], ascending=[True, False]).drop_duplicates('股票代码')
    
    # --- 2. 行业 ---
    df_i = pd.DataFrame()
    if os.path.exists(closing_dir):
        files = sorted(glob.glob(os.path.join(closing_dir, "*.csv")), reverse=True)[:5]
        i_list = []
        for f in files:
            try:
                try: df = pd.read_csv(f, encoding='gbk', dtype=str)
                except: df = pd.read_csv(f, encoding='utf-8-sig', dtype=str)
                
                df.rename(columns={'代码': '股票代码'}, inplace=True)
                ind_col = next((c for c in df.columns if '所属同花顺行业' in c), None)
                
                if ind_col:
                    df.rename(columns={ind_col: '所属行业'}, inplace=True)
                    df['股票代码'] = df['股票代码'].apply(format_code)
                    df['file_date'] = os.path.basename(f)[:10]
                    i_list.append(df[['股票代码', '所属行业', 'file_date']])
            except: pass
        if i_list:
            df_i = pd.concat(i_list).sort_values(by=['file_date'], ascending=False).drop_duplicates('股票代码')

    # --- 3. 涨停原因 ---
    reason_dict = {}
    if os.path.exists(zt_dir):
        files = sorted(glob.glob(os.path.join(zt_dir, "*.csv")), reverse=True)[:30]
        for f in files:
            try:
                try: df = pd.read_csv(f, encoding='gbk', dtype=str)
                except: df = pd.read_csv(f, encoding='utf-8-sig', dtype=str)
                
                col_code = next((c for c in ['code', '股票代码', '代码'] if c in df.columns), None)
                reason_cols = [c for c in df.columns if '涨停原因类别' in c]
                
                if col_code and reason_cols:
                    for _, row in df.iterrows():
                        code = format_code(row[col_code])
                        reason = str(row[reason_cols[0]])
                        if reason and reason not in ['nan', 'None', '-']:
                            parts = [p.strip() for p in reason.split('+') if p.strip()]
                            if code not in reason_dict: reason_dict[code] = []
                            reason_dict[code].extend(parts)
            except: pass

    processed_reasons = {k: "+".join(list(dict.fromkeys(v))) for k, v in reason_dict.items()}

    # --- 4. 合并 ---
    print("  🔄 执行合并...")
    if not df_i.empty:
        final_df = pd.merge(df_c[['股票代码', '股票简称', '所属概念']], 
                            df_i[['股票代码', '所属行业']], 
                            on='股票代码', how='left')
    else:
        final_df = df_c[['股票代码', '股票简称', '所属概念']].copy()
        final_df['所属行业'] = ''

    final_df['历史涨停原因类别'] = final_df['股票代码'].map(processed_reasons).fillna('')
    final_df['code'] = final_df['股票代码']

    cols = ['股票代码', '股票简称', '所属概念', '历史涨停原因类别', '所属行业', 'code']
    for c in cols:
        if c not in final_df.columns: final_df[c] = ''
    final_df = final_df[cols]

    os.makedirs(os.path.dirname(CONCEPT_PATH), exist_ok=True)
    final_df.to_csv(CONCEPT_PATH, index=False, encoding='utf-8-sig')
    print(f"✅ 更新成功: {len(final_df)} 条")

if __name__ == '__main__':
    target_date = get_closest_trade_date()
    if target_date:
        if run_downloads(target_date):
            process_and_merge_files()
        else:
            sys.exit(1)
    else:

        sys.exit(0)
