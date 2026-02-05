from pathlib import Path
import os

# ==================== 路径配置 ====================
# 使用相对路径，确保在 GitHub Actions 和 Streamlit Cloud 都能运行
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / 'data' / 'raw'
METADATA_DIR = BASE_DIR / 'metadata'
CONCEPT_PATH = METADATA_DIR / '所属概念.csv'
CALENDAR_PATH = METADATA_DIR / '交易日历.csv'
SAVE_DIR = BASE_DIR / 'analysis_results'

# 在 config.py 中补充
MARKET_REPORT_DIR = SAVE_DIR / 'market_daily'  # 专门存放市场分析结果
MARKET_REPORT_DIR.mkdir(parents=True, exist_ok=True) # 自动创建

# 趋势表的文件路径
SENTIMENT_TREND_PATH = MARKET_REPORT_DIR / 'daily_sentiment_trend.csv'

# 确保必要的目录存在
for d in [DATA_DIR, SAVE_DIR, METADATA_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# config.py 补充内容

# --- 数据下载与合并专用路径 ---
THS_DATA_ROOT = DATA_DIR.parent / '同花顺所属概念更新'
DOWNLOAD_CONFIGS = {
    '所属概念': {
        'backup_dir': THS_DATA_ROOT / '所属概念',
        'query': '所属概念;股票代码;所属概念数量'
    },
    '收盘数据': {
        'backup_dir': THS_DATA_ROOT / '收盘',
        'query': '收盘价;所属同花顺行业;股票代码'
    },
    '涨跌停数据': {
        'backup_dir': THS_DATA_ROOT / '涨停',
        'query': '涨停原因类别;股票代码'
    }
}

# 自动创建下载目录
for conf in DOWNLOAD_CONFIGS.values():
    conf['backup_dir'].mkdir(parents=True, exist_ok=True)

# ==================== 业务配置 ====================
HOT_KEYWORDS = ['海南', '海峡两岸', '商业航天', '电子化学', '脑机', '光刻胶']
HOT_CONCEPT_LIST = ['海南', '海峡两岸', '商业航天']

BLACKLIST = {
    '融资融券', '深股通', '沪股通', '转融通标的', '证金持股',
    'MSCI概念', '标普道琼斯A股', '沪深300', '预盈预增',
    '地方国资改革', '国企改革'
}

COLUMN_MAPPING = {
    "code": "股票代码", "name": "股票简称","涨跌(%)": "涨跌幅", "成交额(万)": "成交额",
    "now": "收盘价","close": "昨收盘","open": "竞价价","high": "最高价","low": "最低价",
    "bid1": "买一价",
    "bid1_volume": "买一量",
    "ask1": "卖一价",
    "ask1_volume": "卖一量"
}
