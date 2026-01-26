import pandas as pd
from datetime import datetime,timedelta
from typing import Optional, Tuple
from .config import CALENDAR_PATH, DATA_DIR, CONCEPT_PATH
from .utils import safe_read_csv, clean_dataframe

# 1. 自动判断服务器时区并转换
def get_beijing_now():
    from datetime import datetime, timedelta, timezone
    # 直接通过 UTC 强制转北京时间，不需要判断系统时区，也就不用 time 模块了
    return datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8)))

def get_trade_dates(count: int = 10) -> list:
    """获取最近的 N 个交易日序列"""
    if not CALENDAR_PATH.exists():
        print(f"❌ 交易日历文件不存在：{CALENDAR_PATH}")
        return []

    df = safe_read_csv(CALENDAR_PATH)
    if df.empty:
        return []
        
    # 处理编码和列名
    date_col = next((c for c in df.columns if 'date' in c.lower()), df.columns[0])
    if date_col.startswith('\ufeff'):
        df.columns = [c[1:] if c.startswith('\ufeff') else c for c in df.columns]
        date_col = date_col[1:]

    df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
    df = df.dropna(subset=[date_col]).sort_values(date_col)
    
    # 时间判定逻辑
    '''
    now = datetime.now()
    # 早上 9:00 前取昨天作为参考起点
    if now.hour < 9:
        reference_today = (now - timedelta(days=1)).date()
    else:
        reference_today = now.date()

    from datetime import datetime, timedelta
    '''


    now_bj = get_beijing_now()
    
    # 后面的逻辑就稳了
    if now_bj.hour < 9:
        reference_today = (now_bj - timedelta(days=1)).date()
    else:
        reference_today = now_bj.date()

    # 在日历中寻找小于等于参考日期的记录
    valid = df[df[date_col].dt.date <= reference_today]
    if valid.empty:
        return []

    # 获取最后 count 个交易日日期
    # 注意：为了后续计算“对比昨日”指标，通常建议多取 1 天（即取 11 天）
    # 这里严格按照要求取最近 10 个有效交易日
    result_dates = valid.iloc[-count:][date_col].dt.date.tolist()
    
    return result_dates


def read_market_data(trade_date: datetime, data_type: str) -> pd.DataFrame:
    """读取并统一市场数据格式，自动识别竞价或收盘"""
    file_path = DATA_DIR / f"{trade_date.strftime('%Y-%m-%d')}_{data_type}.csv"
    df = safe_read_csv(file_path)
    if df.empty:
        return df

    df = clean_dataframe(df)
    
    # 1. 确定当前是【竞价】还是【收盘】
    prefix = "竞价" if "竞价" in data_type else "收盘"
    
    # 2. 统一价格列
    # 逻辑：如果是竞价行情，输出列叫 '竞价价'；如果是收盘行情，输出列叫 '收盘价'
    target_price = '竞价价' if prefix == "竞价" else '收盘价'
    price_cols = [target_price, '涨停价', '跌停价', '开盘价']
    
    for col in price_cols:
        target = next((c for c in [col, col.replace('价', '')] if c in df.columns), None)
        if target:
            df[col] = pd.to_numeric(df[target], errors='coerce').fillna(0)
    
    # 3. 核心修复：统一成交额（动态列名！！）
    # 这里的 output_amt_name 会变成 "竞价金额" 或者 "收盘金额"
    output_amt_name = f"{prefix}金额"
    
    amt_col = next((c for c in ['竞价成交金额', '成交额', '成交额(万)', '总成交额'] if c in df.columns), None)
    if amt_col:
        df[output_amt_name] = pd.to_numeric(df[amt_col], errors='coerce').fillna(0)
        if '万' in amt_col:
            df[output_amt_name] *= 10000

    # 4. 统一涨跌幅
    pct_col = next((c for c in ['涨跌幅', '涨幅', '涨幅%'] if c in df.columns), None)
    if pct_col:
        df['涨跌幅'] = pd.to_numeric(df[pct_col].astype(str).str.replace('%', ''), errors='coerce').fillna(0)

    return df





def load_concept_data() -> pd.DataFrame:
    """加载概念/行业数据"""
    if not CONCEPT_PATH.exists():
        return pd.DataFrame()
    df = safe_read_csv(CONCEPT_PATH)
    if df.empty:
        return pd.DataFrame()
    df['code'] = df['code'].astype(str).str.zfill(6)
    return df[['code', '所属概念', '所属行业','历史涨停原因类别']].drop_duplicates()
