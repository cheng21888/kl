# -*- coding: utf-8 -*-
"""
整合版：支持早盘竞价与收盘复盘自动切换
优化：精简存储空间，加入精准计时启动逻辑
"""

import os
import re
import time
import datetime
import pandas as pd
import easyquotation
import pywencai
import sys
import io
import requests
import json
import hmac
import hashlib
import base64

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')


# ==================== 0. 精准计时等待逻辑 (兼容 UTC/北京时间) ====================
def get_beijing_time():
    """无论系统处于什么时区，始终获取精准的北京时间"""
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))

print(f"⏰ 当前脚本启动时间 (北京): {get_beijing_time().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"⏰ 当前脚本启动时间 (系统本地): {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

def wait_until_target_time(target_hour, target_minute, target_second):
    """等待直到北京时间指定时刻"""
    # 仅在 GitHub 定时任务（schedule）且是早盘时执行等待
    # 如果你想在本地手动运行时也生效，可以去掉 GITHUB_EVENT_NAME 的判断
    is_gh_schedule = os.environ.get("GITHUB_EVENT_NAME") == "schedule"
    
    if is_gh_schedule and target_hour == 9:
        print(f"🚀 检测到 GitHub 定时任务，开始精准对时，目标北京时间: {target_hour:02d}:{target_minute:02d}:{target_second:02d}")
        while True:
            # 获取当前最新的北京时间
            now_bj = get_beijing_time()
            
            # 将当前时间转换为当天总秒数，方便精确对比
            current_total_seconds = now_bj.hour * 3600 + now_bj.minute * 60 + now_bj.second
            target_total_seconds = target_hour * 3600 + target_minute * 60 + target_second
            
            if current_total_seconds >= target_total_seconds:
                print(f"⏰ 已到达或错过目标时间 ({now_bj.strftime('%H:%M:%S')})，立即开始运行...")
                break
            
            # 每 10 秒打印一次进度
            if now_bj.second % 10 == 0:
                remaining = target_total_seconds - current_total_seconds
                print(f"⏳ 等待中... 当前北京时间: {now_bj.strftime('%H:%M:%S')}，距离对时点还差 {remaining} 秒")
            
            time.sleep(1)

# 获取当前北京时间进行初始逻辑判断
now_bj_start = get_beijing_time()

# 逻辑：如果是早盘（9:25之前）运行，则进入等待逻辑
if now_bj_start.hour == 9 and now_bj_start.minute < 25:
    wait_until_target_time(9, 25, 3)

# ==================== 1. 配置与参数 ====================
RAW_DIR = "data/raw"
# CLEAN_DIR 已弃用，不再创建
STOCK_LIST_PATH = "代码.csv"

if not os.path.exists(RAW_DIR): os.makedirs(RAW_DIR, exist_ok=True)

DINGTALK_TOKEN = os.environ.get("DINGTALK_TOKEN")
DINGTALK_SECRET = os.environ.get("DINGTALK_SECRET")

def get_dir_size(path='.'):
    """获取文件夹总大小（MB）"""
    total = 0
    try:
        for entry in os.scandir(path):
            if entry.is_file():
                total += entry.stat().st_size
            elif entry.is_dir():
                total += get_dir_size(entry.path)
    except Exception:
        pass
    return total / (1024 * 1024)

def send_dingtalk_msg(content):
    if not DINGTALK_TOKEN:
        print("未配置钉钉Token，跳过发送")
        return
    
    url = f"https://oapi.dingtalk.com/robot/send?access_token={DINGTALK_TOKEN}"
    if DINGTALK_SECRET:
        timestamp = str(round(time.time() * 1000))
        secret_enc = DINGTALK_SECRET.encode('utf-8')
        string_to_sign = '{}\n{}'.format(timestamp, DINGTALK_SECRET)
        string_to_sign_enc = string_to_sign.encode('utf-8')
        hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
        sign = base64.b64encode(hmac_code).decode('utf-8')
        url += f"&timestamp={timestamp}&sign={sign}"

    headers = {"Content-Type": "application/json"}
    data = {
        "msgtype": "text",
        "text": {"content": content}
    }
    try:
        res = requests.post(url, data=json.dumps(data), headers=headers)
        print(f"钉钉通知结果: {res.text}")
    except Exception as e:
        print(f"发送钉钉通知失败: {e}")

# 修改点：EN2CN 保持通用，不带“昨日”前缀
DESIRED_COLUMNS = [
    '股票代码', '股票简称', '上市日期', '当前价', '收盘价', '开盘价',
    '买一价', '买一量', '卖一价', '卖一量', '时间戳', '涨跌额', '涨跌幅',
    '最高价', '最低价', '成交量', '成交额', '换手率', '振幅', '流通市值',
    '总市值', '涨停价', '跌停价', '量比', '涨跌停', '连续涨停天数',
    '连续跌停天数', '首次涨停时间', '最终涨停时间', '涨停原因类别',
    '首次跌停时间', '最终跌停时间', '跌停原因类型'
]

# 字典：列名翻译
EN2CN = {
    'name': '股票简称', 'code': '股票代码', 'now': '当前价', 'close': '收盘价',
    'open': '开盘价', 'volume': '成交量1', 'bid_volume': '买量', 'ask_volume': '卖量',
    'bid1': '买一价', 'bid1_volume': '买一量', 'ask1': '卖一价', 'ask1_volume': '卖一量',
    'datetime': '时间戳', '涨跌': '涨跌额', '涨跌(%)': '涨跌幅', 'high': '最高价',
    'low': '最低价', '成交量(手)': '成交量', '成交额(万)': '成交额', 'turnover': '换手率',
    'high_2': '2日最高', 'low_2': '2日最低', '股票简称': '股票简称', 'code_name': '股票简称',
    '涨跌停': '涨跌停', '连续涨停天数': '连续涨停天数'
}

# ==================== 2. 工具函数 ====================

def is_save_time():
    # 1. 检查是否为 GitHub Actions 环境中的手动或外部触发
    event_name = os.environ.get("GITHUB_EVENT_NAME")
    
    # workflow_dispatch 是你在 GitHub 页面点运行
    # repository_dispatch 是你从 Streamlit 按钮点运行
    if event_name in ["workflow_dispatch", "repository_dispatch"]:
        print(f"💡 检测到触发源为 {event_name}，将强制保存数据...")
        return True
        
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).time()
    morning = datetime.time(9, 25) <= now <= datetime.time(9, 30)
    afternoon = datetime.time(15, 0) <= now <= datetime.time(16, 0)
    return morning or afternoon

def clean_data(df, is_index=False):
    if df is None or df.empty: return pd.DataFrame()
    df.columns = [re.sub(r'\[.*\]|:.*', '', str(c)) for c in df.columns]
    df = df.rename(columns={k: EN2CN.get(k, k) for k in df.columns})
    df = df.loc[:, ~df.columns.duplicated()].copy()
    if '股票代码' in df.columns and not is_index:
        df['股票代码'] = df['股票代码'].apply(lambda x: re.findall(r'\d{6}', str(x))[0] if re.findall(r'\d{6}', str(x)) else None)
        df = df.dropna(subset=['股票代码'])
    return df

# ==================== 3. 执行流程 ====================

# --- 1. 获取名单 ---
try:
    df_stocks = pd.read_csv(STOCK_LIST_PATH, dtype={'code': str})
    now_t = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).time()
    if datetime.time(9, 20) <= now_t <= datetime.time(9, 45):
        print("🕒 竞价时段，正在同步本月新股名单...")
        df_new = pywencai.get(question='本月上市的新股', loop=True)
        if df_new is not None and not df_new.empty:
            df_new_clean = df_new[['code', '股票简称']].rename(columns={'股票简称':'code_name'})
            df_stocks = pd.concat([df_stocks, df_new_clean]).drop_duplicates(subset=['code']).reset_index(drop=True)
            df_stocks.to_csv(STOCK_LIST_PATH, index=False, encoding='utf-8-sig')
            print("✅ 名单更新完成")
            print(f"⏰ 当前脚本执行时间 (北京): {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
except Exception as e:
    print(f"⚠️ 名单读取或更新跳过: {e}")

codes = df_stocks['code'].apply(lambda x: re.sub(r'\D', '', str(x))).tolist()

# --- 2. 获取行情 ---
quotation = easyquotation.use('qq')
df_real = pd.DataFrame()
for i in range(3):
    try:
        raw_map = quotation.stocks(codes, prefix=True)
        if raw_map:
            df_real = pd.DataFrame(raw_map).T
            print(f"✅ 行情获取成功 (第{i+1}次)")
            print(f"⏰ 当前脚本执行时间 (北京): {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            break
    except: time.sleep(2)

df_index = pd.DataFrame(quotation.stocks(['sh000001', 'sz399001', 'sz399006'], prefix=True)).T

# --- 3. 动态获取涨跌停 ---
now_hour = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).hour
target_q = '昨日涨跌停' if now_hour < 12 else '涨跌停'

df_yest = pd.DataFrame()
for i in range(3):
    try:
        tmp = pywencai.get(question=target_q, loop=True)
        if tmp is not None and not tmp.empty:
            df_yest = tmp.drop_duplicates(subset=['股票代码'])
            print(f"✅ {target_q}获取成功 (第{i+1}次)")
            print(f"⏰ 当前脚本执行时间 (北京): {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            break
    except: time.sleep(2)

# --- 4. 清洗 ---
df_real_c = clean_data(df_real)
df_index_c = clean_data(df_index, is_index=True)
df_yest_c = clean_data(df_yest)

# --- 5. 合并与统计 ---
if not df_real_c.empty:
    df_real_c['成交额'] = pd.to_numeric(df_real_c['成交额'], errors='coerce').fillna(0)
    total = df_real_c['成交额'].sum()
    sh_val = df_real_c[df_real_c['股票代码'].str.startswith('6')]['成交额'].sum()
    cyb_val = df_real_c[df_real_c['股票代码'].str.startswith('3')]['成交额'].sum()
    stats_msg = f"💰 市场总成交: {total/1e8:.2f}亿 | 🏛️ 沪市: {sh_val/1e8:.2f}亿 | 🏛️ 创业板: {cyb_val/1e8:.2f}亿"
    print(stats_msg)

    # --- 6. 最终保存 ---
    curr_date = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime("%Y-%m-%d")
    if is_save_time():
        suffix = "竞价" if now_hour < 12 else "收盘"
        
        # 优化：仅保留用户指定的列名
        KEEP_COLS = [
            'name', 'code', 'now', 'close', 'open', 'volume', 'bid1', 'bid1_volume', 
            'ask1', 'ask1_volume', '涨跌(%)', 'high', 'low', '成交量(手)', '成交额(万)', 
            'turnover', '振幅', '流通市值', '总市值', '涨停价', '跌停价', '量比'
        ]
        
        # 仅对行情数据进行列精简
        df_real_filtered = df_real.reindex(columns=[c for c in KEEP_COLS if c in df_real.columns]) if df_real is not None else None
        
        # 优化：仅保存核心行情、指数和涨跌停数据
        raw_map = {
            f"{suffix}行情": df_real_filtered, 
            f"{suffix}指数": df_index, 
            f"{suffix}涨跌停": df_yest
        }
        for name, data in raw_map.items():
            if data is not None:
                data.to_csv(os.path.join(RAW_DIR, f"{curr_date}_{name}.csv"), index=False, encoding='utf-8-sig')
        
        # 统计存储状态
        raw_files = os.listdir(RAW_DIR) if os.path.exists(RAW_DIR) else []
        dates = set([f.split('_')[0] for f in raw_files if '_' in f])
        days_count = len(dates)
        storage_size = get_dir_size('data')
        
        storage_msg = f"📊 存储统计: 已存 {days_count} 日数据 | 占用 {storage_size:.2f}MB"
        if storage_size > 400:
            storage_msg += "\n⚠️ 存储空间超过400MB，请及时清理历史数据！"
            
        # 优化：不再保存 CLEAN_DIR 下的文件，以节约空间
        msg = f"【股票分析Github】🚀 {curr_date} {suffix}数据已保存\n{stats_msg}\n{storage_msg}"
        print(msg)
        send_dingtalk_msg(msg)
        print(f"⏰ 当前脚本执行时间 (北京): {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        msg = f"【股票分析Github】ℹ️ 脚本运行完成，但当前时间不在保存时段内。"
        print(msg)
        send_dingtalk_msg(msg)
        print(f"⏰ 当前脚本执行时间 (北京): {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
else:
    msg = "【股票分析Github】⚠️ 未获取到行情数据，请检查网络或代码列表。"
    print(msg)
    send_dingtalk_msg(msg)
    print(f"⏰ 当前脚本执行时间 (北京): {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
