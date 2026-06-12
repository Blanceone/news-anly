import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # AI Model
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    # Feishu
    FEISHU_WEBHOOK_URL = os.getenv("FEISHU_WEBHOOK_URL", "")

    # Stock Watchlist
    STOCK_WATCHLIST = [s.strip() for s in os.getenv("STOCK_WATCHLIST", "").split(",") if s.strip()]

    # Run mode
    RUN_MODE = os.getenv("RUN_MODE", "all")

    # Data sources config
    NEWS_SOURCES = {
        "cls": {
            "name": "财联社",
            "url": "https://www.cls.cn/telegraph",
            "type": "api",
            "api_url": "https://www.cls.cn/v1/roll/get_roll_list",
            "params": {
                "app": "CailianpressWeb",
                "os": "web",
                "sv": "7.7.5",
                "rn": "30",
            },
            "headers": {
                "Referer": "https://www.cls.cn/telegraph",
            },
        },
        "cninfo": {
            "name": "巨潮资讯",
            "url": "http://www.cninfo.com.cn/new/commonUrl/pageOfSearch?url=disclosure/list/search",
            "type": "api",
            "api_url": "http://www.cninfo.com.cn/new/hisAnnouncement/query",
            "params": {
                "pageNum": 1,
                "pageSize": 30,
                "column": "szse",
                "tabName": "fulltext",
                "plate": "sz,sh,bj",
                "stock": "",
                "searchkey": "",
                "category": "",
                "trade": "",
                "seDate": "",
                "sortName": "code",
                "sortType": "asc",
                "isHLtitle": "true",
            },
        },
    }

    # Sell/buy timing for news impact
    NEWS_CATEGORIES = {
        "宏观经济": ["GDP", "CPI", "PMI", "降息", "降准", "加息", "央", "货币", "财政", "通胀", "通缩", "出口", "进口", "贸易"],
        "政策利好": ["利好", "支持", "扶持", "补贴", "减税", "降费", "放宽", "鼓励", "推动", "促进"],
        "政策利空": ["利空", "监管", "整顿", "查处", "处罚", "限制", "收紧", "整改", "约谈"],
        "公司利好": ["业绩预增", "中标", "签约", "增持", "回购", "分红", "送转", "突破", "创新高"],
        "公司利空": ["业绩预减", "亏损", "减持", "违约", "债务", "诉讼", "调查", "ST", "退市"],
        "行业动态": ["新能源", "半导体", "芯片", "AI", "人工智能", "医药", "消费", "汽车", "光伏", "锂电", "光伏"],
        "国际市场": ["美联储", "美股", "港股", "北向", "南向", "汇率", "人民币", "美元", "原油", "黄金"],
    }
