import streamlit as st
import pandas as pd
from datetime import datetime
from mod.data_loader import get_trade_dates
from mod.analyzer import analyze_auction_flow, calculate_auto_concepts

def highlight_6_2(row):
    # 1. 定义 6.2 的五个核心条件判定
    c1 = row['家数'] > 10
    c2 = row['红盘率%'] > 75
    c3 = row['平均涨跌%'] > 1.2
    c4 = row['资金增量(亿)'] > 1
    c5 = '突发放量' in str(row['增量先锋'])
    
    # 初始化样式列表（与列数对应）
    styles = [''] * len(row)
    
    # 2. 如果 5 个条件全满足，整行背景变红
    if all([c1, c2, c3, c4, c5]):
        return ['background-color: #FFCCCC; color: black; font-weight: bold'] * len(row)
    
    # 3. 如果不全满足，则对符合条件的单项标淡黄色
    # 对应列名索引：['题材名称', '家数', '红盘率%', '平均涨跌%', '资金增量(亿)', '状态', '增量先锋']
    # 注意：根据你的 DataFrame 列顺序调整索引
    col_map = {
        '家数': c1, '红盘率%': c2, '平均涨跌%': c3, 
        '资金增量(亿)': c4, '增量先锋': c5
    }
    
    for i, col_name in enumerate(row.index):
        if col_name in col_map and col_map[col_name]:
            styles[i] = 'background-color: #FFFFE0; color: black;' # 淡黄色
            
    return styles

@st.cache_data
def render_concept_dashboard(selected_date=None, prev_date=None):
    """
    专门负责渲染题材共振监控表格
    """
    # 移除原始标题，使用NEW_ui_v2.py中带日期的标题
    pass
    
    # 获取日期逻辑
    date_list = get_trade_dates(30)
    if not date_list or len(date_list) < 2:
        st.error("❌ 无法获取交易日期数据")
        return

    # 优先使用外部传入的日期，如果没有(直接运行脚本时)则取最新的
    if selected_date is None:
        today_date = date_list[-1]
        prev_date = date_list[-2]
    else:
        today_date = selected_date
        # 如果没传 prev_date，从列表中找选中日期的前一个
        if prev_date is None:
            try:
                idx = date_list.index(today_date)
                prev_date = date_list[idx-1]
            except:
                prev_date = date_list[-2]

    # 在界面显示当前锁定的分析日期
    st.info(f"📅 当前分析：{today_date.strftime('%Y-%m-%d')} (对比日：{prev_date.strftime('%Y-%m-%d')})")
    
    with st.spinner(f"正在分析题材数据..."):
        try:
            # 1. 执行核心分析逻辑
            result = analyze_auction_flow(today_date, prev_date)
            if result is None:
                st.warning("⚠️ 竞价行情数据尚未下载，请先执行抓取。")
                return

            df, overview = result

            # 2. 计算题材数据
            auto_concept_df = calculate_auto_concepts(df)

            # 3. 题材共振监控表格
            st.subheader("🤖 题材共振监控 (红色为 6.2 强共振方向)")
            
            # 1. 添加临时标记列（内部逻辑，不显示）
            auto_concept_df['is_62'] = (
                (auto_concept_df['家数'] > 10) &
                (auto_concept_df['红盘率%'] > 75) &
                (auto_concept_df['平均涨跌%'] > 1.2) &
                (auto_concept_df['资金增量(亿)'] > 1) &
                (auto_concept_df['增量先锋'].str.contains('突发放量', na=False))
            )

            # 2. 一键排序（符合标记的排在最前，其余按增量资金降序）
            auto_concept_df = auto_concept_df.sort_values(by=['is_62', '平均涨跌%'], ascending=[False, False])

            # 3. 渲染展示（删除标记列）
            styled_df = auto_concept_df.drop(columns=['is_62']).style.apply(highlight_6_2, axis=1)
            
            # 渲染到页面
            st.dataframe(styled_df, width='stretch')

        except Exception as e:
            st.error(f"❌ 分析出错: {e}")
            st.exception(e)

# 保持兼容性
if __name__ == "__main__":
    st.set_page_config(layout="wide")
    render_concept_dashboard()
