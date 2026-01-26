# -*- coding: utf-8 -*-
# aaaa_NEW.py

# =========================================================
# 1. 系统与基础库
# =========================================================
import os
import sys
import datetime
import requests
import numpy as np
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
import re
import time
import io
import json
import hmac
import hashlib
import base64

# =========================================================
# 2. Streamlit 与 绘图库
# =========================================================
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# --- 必须作为第一个 Streamlit 命令 ---
st.set_page_config(page_title="量化复盘系统", layout="wide")

# =========================================================
# 3. 项目路径修复 (确保能够正确识别 modules 文件夹)
# =========================================================
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

# =========================================================
# 4. 导入自定义模块 (从 modules 文件夹)
# =========================================================
# 配置与通用工具
from mod.config import *
from mod.utils import (
    Logger, safe_read_csv, standardize_code,
    clean_dataframe, check_password, trigger_github_action
)

# 数据加载与核心分析逻辑
from mod.data_loader import get_trade_dates, read_market_data
from mod.analyzer_market import (
    get_sentiment_trend_report,
)
from mod.markdown import render_auction_report_tab  # 引入新封装的函数
  # 引入新封装的函数
from mod.trend_analyzer import display_trend_analysis
# UI 渲染页面 (分模块)
from mod.ui_sentiment import render_sentiment_dashboard
from mod.ui_top_stocks import render_top_turnover_page

# =========================================================
# 5. 定义 huoqu() 函数 (从 main.py 复制过来)
# =========================================================
import easyquotation
import pywencai

def get_beijing_time():
    """无论系统处于什么时区，始终获取精准的北京时间"""
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))

def wait_until_target_time(target_hour, target_minute, target_second):
    """等待直到北京时间指定时刻"""
    # 仅在 GitHub 定时任务（schedule）且是早盘时执行等待
    # 如果你想在本地手动运行时也生效，可以去掉 GITHUB_EVENT_NAME 的判断
    # is_gh_schedule = os.environ.get("GITHUB_EVENT_NAME") == "schedule"

    if target_hour == 9:
        st.info(f"🔧 检测到 GitHub 定时任务，开始精准对时，目标北京时间: {target_hour:02d}:{target_minute:02d}:{target_second:02d}")
        while True:
            # 获取当前最新的北京时间
            now_bj = get_beijing_time()

            # 将当前时间转换为当天总秒数，方便精确对比
            current_total_seconds = now_bj.hour * 3600 + now_bj.minute * 60 + now_bj.second
            target_total_seconds = target_hour * 3600 + target_minute * 60 + target_second

            if current_total_seconds >= target_total_seconds:
                st.success(f"✅ 已到达或错过目标时间 ({now_bj.strftime('%H:%M:%S')})，立即开始运行...")
                break

            # 每 10 秒打印一次进度
            if now_bj.second % 10 == 0:
                remaining = target_total_seconds - current_total_seconds
                st.info(f"⏳ 等待中... 当前北京时间: {now_bj.strftime('%H:%M:%S')}，距离对时点还差 {remaining} 秒")

            time.sleep(1)

def is_save_time():
    """判断是否为保存时间"""
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).time()
    morning = datetime.time(9, 25) <= now <= datetime.time(9, 30)
    afternoon = datetime.time(15, 0) <= now <= datetime.time(20, 0)
    return morning or afternoon

def clean_data(df, is_index=False):
    """清洗数据"""
    if df is None or df.empty:
        return pd.DataFrame()

    # 清理列名
    df.columns = [re.sub(r'\[.*\]|:.*', '', str(c)) for c in df.columns]

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

    df = df.rename(columns={k: EN2CN.get(k, k) for k in df.columns})
    df = df.loc[:, ~df.columns.duplicated()].copy()

    if '股票代码' in df.columns and not is_index:
        df['股票代码'] = df['股票代码'].apply(lambda x: re.findall(r'\d{6}', str(x))[0] if re.findall(r'\d{6}', str(x)) else None)
        df = df.dropna(subset=['股票代码'])

    return df

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
    """发送钉钉消息"""
    DINGTALK_TOKEN = os.environ.get("DINGTALK_TOKEN")
    DINGTALK_SECRET = os.environ.get("DINGTALK_SECRET")

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
        return f"钉钉通知结果: {res.text}"
    except Exception as e:
        return f"发送钉钉通知失败: {e}"

def huoqu():
    """获取股票数据的主函数"""
    RAW_DIR = "data/raw"
    STOCK_LIST_PATH = "代码.csv"

    if not os.path.exists(RAW_DIR):
        os.makedirs(RAW_DIR, exist_ok=True)

    # 使用 Streamlit 的进度和状态显示
    progress_bar = st.progress(0)
    status_text = st.empty()

    # 步骤 1: 获取名单
    status_text.text("📋 正在读取股票代码列表...")
    progress_bar.progress(10)

    try:
        df_stocks = pd.read_csv(STOCK_LIST_PATH, dtype={'code': str})
        now_t = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).time()

        if datetime.time(9, 20) <= now_t <= datetime.time(9, 45):
            status_text.text("🔄 竞价时段，正在同步本月新股名单...")
            progress_bar.progress(20)

            df_new = pywencai.get(question='本月上市的新股', loop=True)
            if df_new is not None and not df_new.empty:
                df_new_clean = df_new[['code', '股票简称']].rename(columns={'股票简称':'code_name'})
                df_stocks = pd.concat([df_stocks, df_new_clean]).drop_duplicates(subset=['code']).reset_index(drop=True)
                df_stocks.to_csv(STOCK_LIST_PATH, index=False, encoding='utf-8-sig')
                status_text.text("✅ 名单更新完成")
    except Exception as e:
        status_text.text(f"⚠️ 名单读取或更新跳过: {e}")

    codes = df_stocks['code'].apply(lambda x: re.sub(r'\D', '', str(x))).tolist()

    # 步骤 2: 获取行情数据
    status_text.text("📈 正在获取实时行情数据...")
    progress_bar.progress(40)

    quotation = easyquotation.use('qq')
    df_real = pd.DataFrame()

    for i in range(3):
        try:
            raw_map = quotation.stocks(codes, prefix=True)
            if raw_map:
                df_real = pd.DataFrame(raw_map).T
                status_text.text(f"✅ 行情获取成功 (第{i+1}次)")
                break
        except Exception as e:
            if i == 2:
                status_text.text(f"❌ 行情获取失败: {e}")
            time.sleep(2)

    progress_bar.progress(60)

    # 获取指数数据
    df_index = pd.DataFrame(quotation.stocks(['sh000001', 'sz399001', 'sz399006'], prefix=True)).T

    # 步骤 3: 动态获取涨跌停数据
    status_text.text("📊 正在获取涨跌停数据...")
    progress_bar.progress(70)

    now_hour = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).hour
    target_q = '昨日涨跌停' if now_hour < 12 else '涨跌停'

    df_yest = pd.DataFrame()
    for i in range(3):
        try:
            tmp = pywencai.get(question=target_q, loop=True)
            if tmp is not None and not tmp.empty:
                df_yest = tmp.drop_duplicates(subset=['股票代码'])
                status_text.text(f"✅ {target_q}获取成功 (第{i+1}次)")
                break
        except Exception as e:
            if i == 2:
                status_text.text(f"❌ 涨跌停数据获取失败: {e}")
            time.sleep(2)

    progress_bar.progress(80)

    # 步骤 4: 清洗数据
    status_text.text("🧹 正在清洗数据...")
    df_real_c = clean_data(df_real)
    df_index_c = clean_data(df_index, is_index=True)
    df_yest_c = clean_data(df_yest)

    progress_bar.progress(90)

    # 步骤 5: 合并与统计
    result_message = ""
    if not df_real_c.empty:
        df_real_c['成交额'] = pd.to_numeric(df_real_c['成交额'], errors='coerce').fillna(0)
        total = df_real_c['成交额'].sum()
        sh_val = df_real_c[df_real_c['股票代码'].str.startswith('6')]['成交额'].sum()
        cyb_val = df_real_c[df_real_c['股票代码'].str.startswith('3')]['成交额'].sum()
        stats_msg = f"📊 市场总成交: {total/1e8:.2f}亿 | 📈 沪市: {sh_val/1e8:.2f}亿 | 📉 创业板: {cyb_val/1e8:.2f}亿"
        result_message += stats_msg + "\n"

        # 步骤 6: 保存数据
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

            # 保存数据
            raw_map = {
                f"{suffix}行情": df_real_filtered,
                f"{suffix}指数": df_index,
                f"{suffix}涨跌停": df_yest
            }

            for name, data in raw_map.items():
                if data is not None:
                    try:
                        data.to_csv(os.path.join(RAW_DIR, f"{curr_date}_{name}.csv"), index=False, encoding='utf-8-sig')
                    except Exception as e:
                        result_message += f"❌ 保存{name}数据失败: {e}\n"

            # 统计存储状态
            raw_files = os.listdir(RAW_DIR) if os.path.exists(RAW_DIR) else []
            dates = set([f.split('_')[0] for f in raw_files if '_' in f])
            days_count = len(dates)
            storage_size = get_dir_size('data')

            storage_msg = f"💾 存储统计: 已存 {days_count} 日数据 | 占用 {storage_size:.2f}MB"
            if storage_size > 400:
                storage_msg += "\n⚠️ 存储空间超过400MB，请及时清理历史数据！"

            result_message += storage_msg + "\n"

            # 发送钉钉通知
            msg = f"【股票分析】📊 {curr_date} {suffix}数据已保存\n{stats_msg}\n{storage_msg}"
            dingtalk_result = send_dingtalk_msg(msg)
            result_message += f"📱 {dingtalk_result}\n"
        else:
            msg = f"【股票分析】⚠️ 脚本运行完成，但当前时间不在保存时段内。"
            result_message += msg + "\n"
            dingtalk_result = send_dingtalk_msg(msg)
            result_message += f"📱 {dingtalk_result}\n"
    else:
        msg = "【股票分析】❌ 未获取到行情数据，请检查网络或代码列表。"
        result_message += msg + "\n"
        dingtalk_result = send_dingtalk_msg(msg)
        result_message += f"📱 {dingtalk_result}\n"

    progress_bar.progress(100)
    status_text.text("✅ 数据获取完成！")

    return result_message

# =========================================================
# 6. 后续逻辑开始 (if check_password(): ...)
# =========================================================

# 1. 页面配置
st.set_page_config(page_title="量化复盘系统", layout="wide")

# 2. 身份校验
if check_password():
    # 3. 全局数据加载
    LOOKBACK_DAYS = 30
    trade_dates = get_trade_dates(LOOKBACK_DAYS)
    report_df = get_sentiment_trend_report(trade_dates)

    # --- A. 初始化页面状态 (确保默认有值) ---
    if 'active_page' not in st.session_state:
        st.session_state.active_page = "📈 市场情绪"

    # 4. 侧边栏控制
    with st.sidebar:
        st.title("🎯 功能导航")

        # --- B. 导航按钮区 (使用你要求的简洁按钮) ---
        if st.button("📈 市场情绪", use_container_width=True):
            st.session_state.active_page = "📈 市场情绪"

        if st.button("🏆 成交榜单", use_container_width=True):
            st.session_state.active_page = "🏆 成交榜单"

        if st.button("🚀 竞价深度分析", use_container_width=True):
            st.session_state.active_page = "🚀 竞价深度分析"

        if st.button("📊 个股趋势分析", use_container_width=True):
            st.session_state.active_page = "📊 个股趋势分析"


        # 增加间距把控制中心压下去
        st.markdown("<br>" * 5, unsafe_allow_html=True)

        # --- C. 控制中心 ---
        with st.expander("⚙️ 控制中心", expanded=True):
            # 日期选择
            all_dates = pd.to_datetime(report_df['日期']).dt.date
            target_date = st.date_input("目标日期", value=all_dates.max())

            st.markdown("---")
            # 两个核心功能按钮
            if st.button("🚀 触发数据抓取", use_container_width=True):
                with st.spinner("正在抓取数据..."):
                    result = huoqu()
                    st.success("数据抓取完成！")
                    with st.expander("查看详细结果", expanded=False):
                        st.text(result)

            if st.button("🔄 同步最新数据", use_container_width=True):
                st.cache_data.clear()
                st.rerun()

    # =========================================================
    # 5. 主页面渲染逻辑 (严格保留你的切片逻辑)
    # =========================================================
    target_date_str = target_date.strftime('%Y-%m-%d')

    # 使用 st.session_state.active_page 来判断当前页
    if st.session_state.active_page == "📈 市场情绪":
        selected_indices = report_df[report_df['日期'] == target_date_str].index.tolist()
        if selected_indices:
            # 动态切片：从头开始截取到选中日期，保证趋势图完整
            display_df = report_df.loc[:selected_indices[0]]
            render_sentiment_dashboard(display_df)
        else:
            st.error(f"未找到 {target_date_str} 的分析数据")

    elif st.session_state.active_page == "🏆 成交榜单":
        # 渲染成交额榜单页
        render_top_turnover_page(target_date)

    elif st.session_state.active_page == "🚀 竞价深度分析":
        render_auction_report_tab(selected_date=target_date)

    elif st.session_state.active_page == "📊 个股趋势分析":
        # target_date 是你侧边栏 date_input 选中的日期
        display_trend_analysis(target_date)
