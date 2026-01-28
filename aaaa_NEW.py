
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
from modules.config import *
from modules.utils import (
    Logger, safe_read_csv, standardize_code, trigger_action,
    clean_dataframe, check_password,
)

# 数据加载与核心分析逻辑
from modules.data_loader import get_trade_dates, read_market_data
from modules.analyzer_market import (
    get_sentiment_trend_report, 
)
from modules.main_markdown import render_auction_report_tab  # 引入新封装的函数
from modules.trend_analyzer import display_trend_analysis
# UI 渲染页面 (分模块)
from modules.ui_sentiment import render_sentiment_dashboard
from modules.ui_top_stocks import render_top_turnover_page

# =========================================================
# 5. 后续逻辑开始 (if check_password(): ...)
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
            if st.button("🔄 同步最新数据", use_container_width=True):
                st.cache_data.clear()
                st.rerun()            
  
        # 按钮 1：触发更新所属概念 (对应你的 Update Concepts Daily YAML)
            if st.button("🧬 更新所属概念", use_container_width=True):
                trigger_action("concepts_update_trigger") # 确保 YAML 里 types 也是这个名字
                
            # 按钮 2：触发抓取行情数据 (对应你的 Stock Monitor Task YAML)
            if st.button("📊 抓取行情数据", use_container_width=True):
                trigger_action("stock_monitor_trigger") # 确保 YAML 里 types 也是这个名字
        
          


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
