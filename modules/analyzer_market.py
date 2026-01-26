# modules/analyzer_market.py
import pandas as pd
import numpy as np
from concurrent.futures import ThreadPoolExecutor
from modules.data_loader import read_market_data
import streamlit as st
from modules.config import DATA_DIR, SENTIMENT_TREND_PATH

def fast_daily_calc(df: pd.DataFrame, prefix: str):
    """
    使用 NumPy 向量化提速计算11
    """
    if df.empty: return {}

    # 获取标准列名
    amt_col = f"{prefix}金额"
    price_col = f"{prefix}价"
    chg_col = '涨跌幅'
    name_col = '股票简称'
    code_col = '股票代码'

    # 预检查必需列，防止报错
    required = [amt_col, price_col, chg_col, name_col, code_col, '涨停价', '跌停价']
    if not all(c in df.columns for c in required): return {}

    # 转为 NumPy 数组提升性能
    codes = df[code_col].values.astype(str)
    amts = df[amt_col].values
    chgs = df[chg_col].values
    names = df[name_col].values.astype(str)
    prices = df[price_col].values
    limit_up_prices = df['涨停价'].values
    limit_down_prices = df['跌停价'].values

    # 构造常用布尔掩码
    mask_sh = np.char.startswith(codes, 'sh6')
    mask_cyb = np.char.startswith(codes, 'sz3')
# 1. 强化 ST 过滤：涵盖 ST, *ST, SST 以及可能的大小写
    # NumPy 向量化：先转小写，再查是否存在 'st'
    names_lower = np.char.lower(names)
    mask_not_st = (np.char.find(names_lower, 'st') == -1)
    
    # 2. 极高精度涨跌停判定 (使用 0.001 避免浮点数漂移误差)
    # 增加 price > 0 判定，防止停牌股干扰
    # 1. 极高精度价格判定 (0.001)
    # 2. 叠加涨跌幅阈值 (大于 9% 或 小于 -9%)
    is_limit_up = (prices > 0) & (np.abs(prices - limit_up_prices) < 0.001) & (chgs > 9)
    is_limit_down = (prices > 0) & (np.abs(prices - limit_down_prices) < 0.001) & (chgs < -9)

    # 3. 情绪计数逻辑 (确保仅在 mask_not_st 范围内)
    m_valid = mask_not_st
    
    # 涨停/跌停数统计
    count_limit_up = np.sum(is_limit_up & m_valid)
    count_limit_down = np.sum(is_limit_down & m_valid)
    
    # 核心统计计算
    total_amt = np.sum(amts) / 1e8
    sh_amt = np.sum(amts[mask_sh]) / 1e8
    cyb_amt = np.sum(amts[mask_cyb]) / 1e8
    
    # 计算前15股票成交额总额及其与市场总额的比例
    if len(amts) >= 15:
        # 获取前15大成交额
        top15_amts = np.partition(amts, -15)[-15:]
        top15_total = np.sum(top15_amts) / 1e8
        top15_ratio = top15_total / total_amt if total_amt > 0 else 0
    else:
        # 如果股票数量不足15，计算所有股票的成交额
        top15_total = total_amt
        top15_ratio = 1.0

    # 情绪指标计数 (在 not_st 掩码下计算)
    m_valid = mask_not_st
    m_sh_valid = mask_not_st & mask_sh
    m_cyb_valid = mask_not_st & mask_cyb

    raw_stats = {
        '总额': total_amt,
        '上海额': sh_amt,
        '创业额': cyb_amt,
        '前15总额': top15_total,
        '前15占比': top15_ratio,
        '强力': np.sum((chgs >= 7) & m_valid),
        '极弱': np.sum((chgs <= -7) & m_valid),
        '涨停': count_limit_up,
        '跌停': count_limit_down,
        '上涨数': np.sum((chgs > 0) & m_valid),
        '下跌数': np.sum((chgs < 0) & m_valid),
        '沪涨': np.sum((chgs > 0) & m_sh_valid),
        '沪跌': np.sum((chgs < 0) & m_sh_valid),
        '创涨': np.sum((chgs > 0) & m_cyb_valid),
        '创跌': np.sum((chgs < 0) & m_cyb_valid)
    }
    return {f"{prefix}_{k}": v for k, v in raw_stats.items()}

def process_index_data(d, prefix):
    """
    直接读取原始CSV文件提取指数。
    d: datetime对象 (项目内部已处理好的时间)
    prefix: '竞价' 或 '收盘'
    """
    # 1. 初始化默认值字典
    res = {
        f'{prefix}_上证涨跌幅': 0.0,
        f'{prefix}_深证涨跌幅': 0.0,
        f'{prefix}_创业涨跌幅': 0.0
    }

    try:
        # 2. 构造原始文件路径 (d已经是时间对象，直接strftime)
        # 注意：这里确保 DATA_DIR 是 Path 对象，如果是字符串请用 os.path.join
        file_name = f"{d.strftime('%Y-%m-%d')}_{prefix}指数.csv"
        file_path = DATA_DIR / file_name

        if not file_path.exists():
            print(f"⚠️ [DEBUG] 找不到文件: {file_path}")
            return res

        # 3. 直接读取源文件，不走 standardized_code，保留原始的 sh000001
        df_raw = pd.DataFrame()
        for enc in ['gbk', 'utf-8-sig']:
            try:
                # 这里不加 dtype=str，让涨跌幅自动识别为浮点数
                df_raw = pd.read_csv(file_path, encoding=enc)
                break
            except:
                continue

        if df_raw.empty:
            return res

        # 4. 把读取到的原始 DF 丢到变量浏览器里 (变量名为 df_竞价_raw 或 df_收盘_raw)
        # 你可以在 Spyder 的变量浏览器里直接看到它
        globals()[f'df_{prefix}_raw'] = df_raw

        # 5. 建立查找表 (根据你上传的 CSV 列名是 'code' 和 '涨跌(%)')
        # 强制将 code 转为字符串并去空格
        df_raw['code'] = df_raw['code'].astype(str).str.strip().str.lower()
        
        # 自动识别涨跌幅列名（兼容不同版本的CSV）
        pct_col = '涨跌(%)' if '涨跌(%)' in df_raw.columns else '涨跌幅'
        lookup = dict(zip(df_raw['code'], df_raw[pct_col]))

        # 6. 精准填充结果
        res[f'{prefix}_上证涨跌幅'] = float(lookup.get('sh000001', 0.0))
        res[f'{prefix}_深证涨跌幅'] = float(lookup.get('sz399001', 0.0))
        res[f'{prefix}_创业涨跌幅'] = float(lookup.get('sz399006', 0.0))
        
        return res

    except Exception as e:
        print(f"❌ [ERROR] 提取指数失败: {e}")
        return res

def process_single_date(d):
    """单日处理单元"""
    try:
        df_jj = read_market_data(d, '竞价行情')
        df_sp = read_market_data(d, '收盘行情')
        if df_jj.empty and df_sp.empty: return None
        
        res_jj = fast_daily_calc(df_jj, prefix="竞价")
        res_sp = fast_daily_calc(df_sp, prefix="收盘")
        
        # 读取并处理指数数据
        index_jj = process_index_data(d, "竞价")
        index_sp = process_index_data(d, "收盘")
        
        combined = {'日期': d.strftime('%Y-%m-%d'), '_raw_date': d}
        combined.update(res_jj)
        combined.update(res_sp)
        combined.update(index_jj)
        combined.update(index_sp)
        return combined
    except Exception: return None
#@st.cache_data
@st.cache_data(ttl=20000)
def get_sentiment_trend_report(date_list: list):
    """一日一行，增量对齐更新逻辑"""
    # 1. 加载已有数据
    old_df = pd.DataFrame()
    if SENTIMENT_TREND_PATH.exists():
        try:
            # 读取时确保“日期”列为字符串，防止解析错误
            old_df = pd.read_csv(SENTIMENT_TREND_PATH, encoding='utf-8-sig', dtype={'日期': str})
        except Exception as e:
            st.warning(f"读取旧趋势表失败，将重新计算: {e}")

    # 2. 识别待更新日期 (尚未完成“收盘”数据计算的日期)
    processed_dates = set()
    if not old_df.empty and '收盘_总额' in old_df.columns:
        # 认为如果有“收盘_总额”且大于 0，则该日收盘数据已完整
        processed_dates = set(old_df[old_df['收盘_总额'] > 0]['日期'].tolist())
    
    needed_dates = [d for d in date_list if d.strftime('%Y-%m-%d') not in processed_dates]

    # 3. 执行增量计算
    new_results = []
    if needed_dates:
        with ThreadPoolExecutor(max_workers=6) as executor:
            new_results = [r for r in executor.map(process_single_date, needed_dates) if r is not None]
    
    if not new_results and old_df.empty:
        return pd.DataFrame()

    # 4. 合并与日期对齐
    new_df = pd.DataFrame(new_results)
    if not old_df.empty:
        # 补全 old_df 的 _raw_date 用于后续排序
        if '_raw_date' not in old_df.columns:
            old_df['_raw_date'] = pd.to_datetime(old_df['日期'])
        combined_df = pd.concat([old_df, new_df], ignore_index=True)
    else:
        combined_df = new_df

    # 统一转换 _raw_date 为 pandas datetime 格式，解决 Timestamp 与 date 无法比较的问题
    combined_df['_raw_date'] = pd.to_datetime(combined_df['_raw_date'])

    # 5. 去重策略：按日期排序，保留最后一条（覆盖上午的“仅竞价”数据）
    combined_df = combined_df.sort_values('_raw_date').drop_duplicates(subset=['日期'], keep='last')

    # 6. 重新计算所有衍生指标（确保 diff 等计算的连续性）
    # 将数值列中的 NaN 填充为 0
    numeric_cols = combined_df.select_dtypes(include=[np.number]).columns
    combined_df[numeric_cols] = combined_df[numeric_cols].fillna(0)

    for p in ['竞价', '收盘']:
        # 确保基础统计列存在
        for k in ['总额', '上海额', '创业额', '上涨数', '下跌数', '沪涨', '沪跌', '创涨', '创跌', '涨停', '跌停', '强力', '极弱']:
            col = f"{p}_{k}"
            if col not in combined_df.columns:
                combined_df[col] = 0.0

        # 资金维度 (4列)
        combined_df[f'{p}_资金增减'] = combined_df[f'{p}_总额'].diff()
        combined_df[f'{p}_增减幅'] = combined_df[f'{p}_总额'].pct_change()
        combined_df[f'{p}_上海差值'] = combined_df[f'{p}_上海额'].diff()
        combined_df[f'{p}_创业差值'] = combined_df[f'{p}_创业额'].diff()

        # 涨跌比维度 (3列)
        combined_df[f'{p}_全场涨跌比'] = combined_df[f'{p}_上涨数'] / combined_df[f'{p}_下跌数'].replace(0, 1)
        combined_df[f'{p}_上海涨跌比'] = combined_df[f'{p}_沪涨'] / combined_df[f'{p}_沪跌'].replace(0, 1)
        combined_df[f'{p}_创业涨跌比'] = combined_df[f'{p}_创涨'] / combined_df[f'{p}_创跌'].replace(0, 1)

        # 情绪波动维度 (4列)
        combined_df[f'{p}_涨停_diff'] = combined_df[f'{p}_涨停'].diff()
        combined_df[f'{p}_跌停_diff'] = combined_df[f'{p}_跌停'].diff()
        combined_df[f'{p}_强力_diff'] = combined_df[f'{p}_强力'].diff()
        combined_df[f'{p}_极弱_diff'] = combined_df[f'{p}_极弱'].diff()

        # 4. 连续性校验：如果今日或昨日总额为0，则抹平所有衍生变动指标
        mask = (combined_df[f'{p}_总额'] == 0) | (combined_df[f'{p}_总额'].shift(1) == 0)
        derived_cols = [
            f'{p}_资金增减', f'{p}_增减幅', f'{p}_上海差值', f'{p}_创业差值',
            f'{p}_涨停_diff', f'{p}_跌停_diff', f'{p}_强力_diff', f'{p}_极弱_diff'
        ]
        combined_df.loc[mask, derived_cols] = 0
        
        # 确保 diff 列为整数类型（在抹平之后转换）
        for col in [f'{p}_涨停_diff', f'{p}_跌停_diff', f'{p}_强力_diff', f'{p}_极弱_diff']:
            combined_df[col] = combined_df[col].fillna(0).astype(int)

    # 7. 最终整理、保留4位小数并安全写回
    final_df = combined_df.drop(columns=['_raw_date']).sort_values('日期').reset_index(drop=True)
    final_df = final_df.round(4)

    try:
        SENTIMENT_TREND_PATH.parent.mkdir(parents=True, exist_ok=True)
        final_df.to_csv(SENTIMENT_TREND_PATH, index=False, encoding='utf-8-sig')
    except Exception as e:
        st.error(f"自动保存趋势报告失败: {e}")

    return final_df
