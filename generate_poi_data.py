#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
POI数据生成器 - 生成10万条模拟POI数据
用于本地出行/游玩路线规划系统
"""

import csv
import json
import random
import time
import os
from datetime import datetime

# ============================================================
# 基础数据配置
# ============================================================

# 城市中心坐标 (经度, 维度)
CITIES = {
    "北京": {"center": (116.407, 39.904), "districts": ["朝阳区", "海淀区", "东城区", "西城区", "丰台区", "石景山区", "通州区", "大兴区", "顺义区", "昌平区"]},
    "上海": {"center": (121.473, 31.230), "districts": ["浦东新区", "黄浦区", "静安区", "徐汇区", "长宁区", "虹口区", "杨浦区", "普陀区", "闵行区", "宝山区"]},
    "广州": {"center": (113.264, 23.130), "districts": ["天河区", "越秀区", "海珠区", "荔湾区", "白云区", "番禺区", "黄埔区", "花都区", "南沙区", "增城区"]},
    "深圳": {"center": (114.058, 22.543), "districts": ["南山区", "福田区", "罗湖区", "宝安区", "龙岗区", "龙华区", "光明区", "坪山区", "盐田区", "大鹏新区"]},
    "成都": {"center": (104.066, 30.573), "districts": ["锦江区", "青羊区", "武侯区", "成华区", "金牛区", "高新区", "天府新区", "龙泉驿区", "温江区", "双流区"]},
    "杭州": {"center": (120.155, 30.275), "districts": ["西湖区", "上城区", "拱墅区", "滨江区", "萧山区", "余杭区", "临平区", "富阳区", "临安区", "钱塘区"]},
    "武汉": {"center": (114.305, 30.593), "districts": ["武昌区", "江汉区", "洪山区", "江岸区", "汉阳区", "青山区", "东西湖区", "蔡甸区", "江夏区", "黄陂区"]},
    "西安": {"center": (108.940, 34.265), "districts": ["雁塔区", "碑林区", "莲湖区", "未央区", "灞桥区", "长安区", "高新区", "曲江新区", "新城区", "高陵区"]},
    "重庆": {"center": (106.551, 29.563), "districts": ["渝中区", "江北区", "南岸区", "沙坪坝区", "九龙坡区", "大渡口区", "渝北区", "巴南区", "北碚区", "两江新区"]},
    "南京": {"center": (118.796, 32.060), "districts": ["玄武区", "秦淮区", "建邺区", "鼓楼区", "栖霞区", "雨花台区", "江宁区", "浦口区", "六合区", "溧水区"]},
    "天津": {"center": (117.201, 39.085), "districts": ["和平区", "河西区", "南开区", "河东区", "河北区", "红桥区", "滨海新区", "西青区", "津南区", "东丽区"]},
    "苏州": {"center": (120.585, 31.299), "districts": ["姑苏区", "虎丘区", "吴中区", "相城区", "吴江区", "工业园区", "昆山市", "太仓市", "常熟市", "张家港市"]},
    "长沙": {"center": (112.939, 28.228), "districts": ["芙蓉区", "天心区", "岳麓区", "开福区", "雨花区", "望城区", "长沙县", "浏阳市", "宁乡市"]},
    "青岛": {"center": (120.383, 36.067), "districts": ["市南区", "市北区", "李沧区", "崂山区", "城阳区", "黄岛区", "即墨区", "胶州市", "平度市", "莱西市"]},
    "郑州": {"center": (113.665, 34.758), "districts": ["金水区", "二七区", "中原区", "管城区", "惠济区", "郑东新区", "高新区", "经开区", "航空港区", "上街区"]},
    "厦门": {"center": (118.089, 24.479), "districts": ["思明区", "湖里区", "集美区", "海沧区", "同安区", "翔安区"]},
    "昆明": {"center": (102.833, 25.019), "districts": ["五华区", "盘龙区", "官渡区", "西山区", "呈贡区", "晋宁区", "东川区", "安宁市"]},
    "大连": {"center": (121.615, 38.914), "districts": ["中山区", "西岗区", "沙河口区", "甘井子区", "金州区", "旅顺口区", "普兰店区", "瓦房店市"]},
    "三亚": {"center": (109.512, 18.253), "districts": ["天涯区", "吉阳区", "海棠区", "崖州区"]},
    "丽江": {"center": (100.227, 26.872), "districts": ["古城区", "玉龙县", "永胜县", "华坪县", "宁蒗县"]},
}

# ============================================================
# POI类别配置
# ============================================================

CATEGORIES = {
    "餐饮": {
        "subcategories": ["中餐", "西餐", "日料", "韩餐", "火锅", "烧烤", "小吃快餐", "甜品饮品", "自助餐", "海鲜", "川菜", "粤菜", "湘菜", "江浙菜", "东北菜", "云南菜", "面馆", "咖啡厅", "茶馆", "酒吧"],
        "avg_cost_range": (15, 800),
        "queue_range": (0, 120),
        "rating_bias": 3.8,
        "weight": 35,  # 占比权重
    },
    "景点": {
        "subcategories": ["自然风光", "历史古迹", "主题公园", "博物馆", "美术馆", "动物园", "植物园", "海洋馆", "古镇古村", "城市地标", "公园", "寺庙", "纪念馆", "展览馆", "观光塔"],
        "avg_cost_range": (0, 500),
        "queue_range": (0, 180),
        "rating_bias": 4.0,
        "weight": 20,
    },
    "娱乐": {
        "subcategories": ["电影院", "KTV", "桌游密室", "剧本杀", "电玩城", "游乐园", "水上乐园", "滑雪场", "高尔夫", "保龄球", "射箭馆", "蹦床公园", "VR体验", "真人CS", "温泉"],
        "avg_cost_range": (30, 600),
        "queue_range": (0, 90),
        "rating_bias": 3.9,
        "weight": 15,
    },
    "文化": {
        "subcategories": ["图书馆", "剧院", "音乐厅", "画廊", "文创园区", "书店", "非遗体验", "手工艺坊", "摄影基地", "文化广场"],
        "avg_cost_range": (0, 300),
        "queue_range": (0, 60),
        "rating_bias": 4.2,
        "weight": 10,
    },
    "购物": {
        "subcategories": ["大型商场", "购物中心", "步行街", "奥特莱斯", "超市", "便利店", "特产店", "花鸟市场", "古玩市场", "夜市"],
        "avg_cost_range": (0, 2000),
        "queue_range": (0, 45),
        "rating_bias": 3.7,
        "weight": 10,
    },
    "运动健身": {
        "subcategories": ["健身房", "游泳馆", "篮球场", "足球场", "网球场", "羽毛球馆", "瑜伽馆", "攀岩馆", "搏击馆", "滑板公园", "骑行道", "跑步公园"],
        "avg_cost_range": (20, 300),
        "queue_range": (0, 30),
        "rating_bias": 4.0,
        "weight": 5,
    },
    "亲子": {
        "subcategories": ["儿童乐园", "亲子餐厅", "科普馆", "少年宫", "儿童剧场", "采摘园", "牧场体验", "手工DIY", "水上乐园", "拓展训练"],
        "avg_cost_range": (30, 400),
        "queue_range": (0, 90),
        "rating_bias": 4.1,
        "weight": 5,
    },
}

CATEGORY_EN_MAP = {
    "餐饮": "food",
    "景点": "attraction",
    "娱乐": "entertainment",
    "文化": "culture",
    "购物": "shopping",
    "运动健身": "fitness",
    "亲子": "family",
}

SUBCATEGORY_EN_MAP = {
    "餐饮": {
        "中餐": "chinese", "西餐": "western", "日料": "japanese", "韩餐": "korean",
        "火锅": "hotpot", "烧烤": "bbq", "小吃快餐": "snack", "甜品饮品": "dessert",
        "自助餐": "buffet", "海鲜": "seafood", "川菜": "sichuan", "粤菜": "cantonese",
        "湘菜": "hunan", "江浙菜": "jiangzhe", "东北菜": "northeast", "云南菜": "yunnan",
        "面馆": "noodles", "咖啡厅": "cafe", "茶馆": "teahouse", "酒吧": "bar",
    },
    "景点": {
        "自然风光": "natural", "历史古迹": "historic", "主题公园": "theme_park",
        "博物馆": "museum", "美术馆": "gallery", "动物园": "zoo", "植物园": "botanical",
        "海洋馆": "aquarium", "古镇古村": "ancient_town", "城市地标": "landmark",
        "公园": "park", "寺庙": "temple", "纪念馆": "memorial", "展览馆": "exhibition",
        "观光塔": "tower",
    },
    "娱乐": {
        "电影院": "cinema", "KTV": "ktv", "桌游密室": "board_game", "剧本杀": "script_kill",
        "电玩城": "arcade", "游乐园": "amusement_park", "水上乐园": "water_park",
        "滑雪场": "ski_resort", "高尔夫": "golf", "保龄球": "bowling", "射箭馆": "archery",
        "蹦床公园": "trampoline", "VR体验": "vr_experience", "真人CS": "paintball",
        "温泉": "hot_spring",
    },
    "文化": {
        "图书馆": "library", "剧院": "theater", "音乐厅": "concert_hall",
        "画廊": "art_gallery", "文创园区": "creative_park", "书店": "bookstore",
        "非遗体验": "heritage", "手工艺坊": "craft_workshop", "摄影基地": "photo_studio",
        "文化广场": "culture_square",
    },
    "购物": {
        "大型商场": "mall", "购物中心": "shopping_center", "步行街": "pedestrian_street",
        "奥特莱斯": "outlet", "超市": "supermarket", "便利店": "convenience",
        "特产店": "souvenir", "花鸟市场": "flower_market", "古玩市场": "antique_market",
        "夜市": "night_market",
    },
    "运动健身": {
        "健身房": "gym", "游泳馆": "swimming", "篮球场": "basketball", "足球场": "football",
        "网球场": "tennis", "羽毛球馆": "badminton", "瑜伽馆": "yoga", "攀岩馆": "climbing",
        "搏击馆": "martial_arts", "滑板公园": "skate_park", "骑行道": "cycling",
        "跑步公园": "running",
    },
    "亲子": {
        "儿童乐园": "kids_play", "亲子餐厅": "family_restaurant", "科普馆": "science_center",
        "少年宫": "children_palace", "儿童剧场": "kids_theater", "采摘园": "picking_garden",
        "牧场体验": "ranch", "手工DIY": "diy_workshop", "水上乐园": "water_park",
        "拓展训练": "outdoor_training",
    },
}

FEATURES_BIAS = {
    "餐饮": {"taste": (0.55, 0.92), "photo": (0.3, 0.75), "queue_risk": (0.4, 0.85),
             "cost_performance": (0.4, 0.85), "quiet": (0.1, 0.5), "indoor": (0.6, 1.0),
             "family_friendly": (0.35, 0.75), "night_view": (0.15, 0.55)},
    "景点": {"taste": (0.05, 0.3), "photo": (0.6, 0.98), "queue_risk": (0.25, 0.8),
             "cost_performance": (0.5, 0.95), "quiet": (0.4, 0.85), "indoor": (0.05, 0.45),
             "family_friendly": (0.55, 0.95), "night_view": (0.3, 0.75)},
    "娱乐": {"taste": (0.05, 0.25), "photo": (0.35, 0.75), "queue_risk": (0.3, 0.75),
             "cost_performance": (0.35, 0.75), "quiet": (0.05, 0.35), "indoor": (0.55, 1.0),
             "family_friendly": (0.3, 0.7), "night_view": (0.1, 0.45)},
    "文化": {"taste": (0.05, 0.2), "photo": (0.55, 0.9), "queue_risk": (0.05, 0.45),
             "cost_performance": (0.6, 0.95), "quiet": (0.65, 1.0), "indoor": (0.6, 1.0),
             "family_friendly": (0.35, 0.7), "night_view": (0.05, 0.35)},
    "购物": {"taste": (0.05, 0.3), "photo": (0.3, 0.7), "queue_risk": (0.2, 0.65),
             "cost_performance": (0.35, 0.75), "quiet": (0.05, 0.35), "indoor": (0.65, 1.0),
             "family_friendly": (0.5, 0.85), "night_view": (0.25, 0.65)},
    "运动健身": {"taste": (0.05, 0.2), "photo": (0.1, 0.4), "queue_risk": (0.05, 0.35),
                 "cost_performance": (0.4, 0.8), "quiet": (0.3, 0.7), "indoor": (0.5, 1.0),
                 "family_friendly": (0.1, 0.45), "night_view": (0.05, 0.25)},
    "亲子": {"taste": (0.2, 0.55), "photo": (0.4, 0.8), "queue_risk": (0.25, 0.7),
             "cost_performance": (0.4, 0.8), "quiet": (0.3, 0.65), "indoor": (0.35, 0.85),
             "family_friendly": (0.8, 1.0), "night_view": (0.05, 0.3)},
}

# ============================================================
# POI名称生成素材
# ============================================================

# 餐饮名称组件
RESTAURANT_PREFIXES = ["老", "小", "大", "金", "银", "红", "绿", "新", "古", "鲜", "香", "辣", "蜀", "粤", "湘", "江南", "塞北", "东海", "西域", "南国", "北国", "天府", "巴蜀", "岭南", "齐鲁", "关中", "江南", "徽州", "闽南", "潮汕"]
RESTAURANT_MIDS = ["张", "李", "王", "刘", "陈", "杨", "赵", "黄", "周", "吴", "徐", "孙", "马", "朱", "胡", "郭", "林", "何", "高", "罗", "郑", "梁", "谢", "宋", "唐", "韩", "冯", "董", "程", "蔡"]
RESTAURANT_SUFFIXES_RESTAURANT = ["餐厅", "饭店", "酒楼", "食府", "小馆", "私房菜", "家常菜", "美食城", "菜馆", "饭庄"]
RESTAURANT_SUFFIXES_HOTPOT = ["火锅", "火锅城", "火锅店", "涮肉坊", "铜锅涮"]
RESTAURANT_SUFFIXES_BBQ = ["烧烤", "烤肉", "烤鱼", "铁板烧", "炭火烤肉"]
RESTAURANT_SUFFIXES_CAFE = ["咖啡", "咖啡馆", "咖啡厅", "茶室", "茶馆", "茶舍", "奶茶店", "甜品店", "烘焙坊"]
RESTAURANT_SUFFIXES_SNACK = ["小吃", "面馆", "粉店", "饺子馆", "包子铺", "煎饼店", "麻辣烫", "米线店", "馄饨店", "粥铺"]

# 景点名称组件
ATTRACTION_TYPES = ["公园", "花园", "景区", "风景区", "旅游区", "度假区", "生态园", "湿地公园", "森林公园", "地质公园", "遗址", "古迹", "故居", "旧址", "纪念馆", "博物院", "展览馆", "美术馆", "科技馆", "天文馆"]
ATTRACTION_PREFIXES = ["国家", "省级", "市级", "东方", "西方", "南方", "北方", "中原", "江南", "塞北", "东海", "西域", "南国", "北国", "天府", "巴蜀", "岭南", "齐鲁", "关中", "徽州", "闽南", "潮汕", "华夏", "神州", "九州", "中华", "龙腾", "凤舞", "山水", "云端", "星空", "月光", "阳光", "清风", "明月", "碧波", "翠竹", "松涛", "梅兰", "竹菊", "桃源", "仙境", "世外", "桃源"]

# 娱乐名称组件
ENTERTAINMENT_PREFIXES = ["欢乐", "开心", "快乐", "疯狂", "奇妙", "梦幻", "星际", "未来", "超级", "酷玩", "乐翻天", "嗨翻天", "玩转", "趣玩", "妙趣", "奇趣", "乐动", "动感", "激情", "飞扬"]

# 通用形容词
ADJECTIVES = ["优雅", "时尚", "经典", "精致", "高端", "大气", "温馨", "浪漫", "复古", "现代", "简约", "奢华", "清幽", "热闹", "繁华", "宁静", "古朴", "典雅", "别致", "独特"]

# 街道名称
STREET_NAMES = ["中山路", "人民路", "解放路", "建设路", "文化路", "和平路", "胜利路", "光明路", "新华路", "长安街", "南京路", "淮海路", "王府井", "春熙路", "上下九", "解放碑", "江汉路", "户部巷", "回民街", "夫子庙", "城隍庙", "步行街", "美食街", "商业街", "小吃街", "文化街", "古镇街", "老街", "新街", "大街", "大道", "广场路", "公园路", "学校路", "医院路", "科技路", "创新路", "发展路", "前进路", "幸福路", "和谐路", "团结路", "友谊路", "爱国路", "敬业路", "诚信路", "友善路"]

# ============================================================
# 标签配置
# ============================================================

TAGS_BY_CATEGORY = {
    "餐饮": ["环境好", "味道好", "分量足", "性价比高", "服务好", "有包间", "可停车", "有WiFi", "24小时营业", "老字号", "网红店", "排队少", "适合聚餐", "适合约会", "适合商务", "适合家庭", "有儿童椅", "可外卖", "有露台", "景观位"],
    "景点": ["免费", "拍照圣地", "遛娃好去处", "适合徒步", "历史底蕴", "自然风光", "网红打卡", "人少景美", "交通方便", "有讲解", "有导游", "适合老人", "适合情侣", "适合团建", "四季皆宜", "春天赏花", "秋天赏叶", "冬天赏雪", "夏天避暑"],
    "娱乐": ["刺激", "解压", "适合团建", "适合约会", "适合朋友聚会", "有教练", "设备新", "场地大", "有空调", "有储物柜", "可团购", "有会员卡", "周末活动", "节假日优惠"],
    "文化": ["文艺", "小众", "有展览", "有活动", "适合学习", "适合拍照", "安静", "免费", "有讲座", "有工作坊", "有纪念品", "有咖啡"],
    "购物": ["品牌齐全", "打折", "免税", "有停车场", "交通方便", "有餐饮", "有影院", "有儿童区", "有休息区", "有WiFi", "有充电桩"],
    "运动健身": ["器械齐全", "有教练", "有淋浴", "有储物柜", "有空调", "场地好", "灯光好", "可预约", "有会员卡", "有团购"],
    "亲子": ["安全", "有监护人陪同区", "适合0-3岁", "适合3-6岁", "适合6-12岁", "有休息区", "有餐饮", "有卫生间", "有停车位", "有活动"],
}

# 营业时间模板
OPENING_HOURS_TEMPLATES = [
    "09:00-22:00", "08:00-21:00", "10:00-22:00", "09:30-21:30",
    "08:30-20:30", "10:00-21:00", "09:00-21:00", "10:00-23:00",
    "11:00-23:00", "10:00-18:00", "08:00-17:30", "09:00-17:00",
    "06:00-22:00", "07:00-21:00", "24小时营业", "14:00-02:00",
    "16:00-00:00", "09:00-18:00", "10:00-20:00", "08:00-22:00",
]

# 描述模板
DESCRIPTION_TEMPLATES = {
    "餐饮": [
        "{name}位于{city}{district}，是一家主营{subcategory}的餐厅。餐厅环境{adj}，菜品口味正宗，食材新鲜，深受本地食客喜爱。招牌菜色香味俱全，{tag}，是{scene}的绝佳选择。",
        "{name}坐落于{city}{district}{street}，以{subcategory}闻名。店内装修{adj}，服务周到热情，菜品分量十足且价格实惠。{tag}，多年来积累了大量忠实顾客。",
        "位于{city}{district}的{name}，专注于{subcategory}美食。餐厅氛围{adj}，每道菜品都精心烹制，色香味俱佳。{tag}，是当地人气餐厅之一。",
    ],
    "景点": [
        "{name}位于{city}{district}，是{city}知名的{subcategory}景点。景区环境优美，空气清新，{tag}。一年四季皆有不同的风景，是休闲度假的好去处。",
        "坐落于{city}{district}的{name}，以其独特的{subcategory}魅力吸引着众多游客。这里{adj}静谧，{tag}，是感受{city}文化底蕴的绝佳之地。",
        "{name}是{city}{district}的标志性{subcategory}景点。这里{adj}大气，景色宜人，{tag}。无论是本地居民还是外地游客，都会被这里的美景所吸引。",
    ],
    "娱乐": [
        "{name}位于{city}{district}，是当地热门的{subcategory}娱乐场所。设施{adj}，项目丰富多样，{tag}。是朋友聚会、情侣约会的不二之选。",
        "坐落于{city}{district}{street}的{name}，提供专业的{subcategory}体验。场馆环境{adj}，设备先进，{tag}，让你尽情释放压力。",
        "{name}是{city}{district}新兴的{subcategory}娱乐地标。装修风格{adj}，氛围感十足，{tag}，深受年轻人喜爱。",
    ],
    "文化": [
        "{name}位于{city}{district}，是{city}重要的{subcategory}文化场所。空间{adj}典雅，藏品丰富，{tag}。定期举办各类文化活动，是感受艺术熏陶的好去处。",
        "坐落于{city}{district}的{name}，以{subcategory}为主题。环境{adj}，文化氛围浓厚，{tag}，是文艺青年的打卡圣地。",
    ],
    "购物": [
        "{name}位于{city}{district}{street}，是{city}知名的{subcategory}购物场所。品牌齐全，环境{adj}，{tag}。是购物休闲的理想之地。",
        "坐落于{city}{district}的{name}，是集购物、餐饮、娱乐于一体的{subcategory}。设施{adj}，服务周到，{tag}，满足一站式消费需求。",
    ],
    "运动健身": [
        "{name}位于{city}{district}，是专业的{subcategory}运动场所。场馆{adj}，器材齐全，{tag}。无论是初学者还是运动达人，都能在这里找到适合自己的项目。",
        "坐落于{city}{district}的{name}，提供高品质{subcategory}服务。环境{adj}，教练专业，{tag}，是健身爱好者的首选之地。",
    ],
    "亲子": [
        "{name}位于{city}{district}，是{city}受欢迎的{subcategory}亲子场所。环境安全{adj}，项目寓教于乐，{tag}。是家长带娃出行的放心之选。",
        "坐落于{city}{district}的{name}，专注于{subcategory}亲子体验。设施{adj}，服务贴心，{tag}，让家长和孩子都能享受美好时光。",
    ],
}

# 使用场景
SCENES = {
    "餐饮": ["朋友聚餐", "家庭聚会", "商务宴请", "情侣约会", "同事小聚", "生日庆祝", "节日聚餐", "日常用餐"],
    "景点": ["周末出游", "节假日旅行", "摄影采风", "亲子活动", "朋友聚会", "情侣出游", "团队活动"],
    "娱乐": ["朋友聚会", "情侣约会", "公司团建", "生日派对", "周末休闲", "解压放松"],
    "文化": ["文艺打卡", "学习充电", "周末休闲", "约会", "亲子活动", "朋友聚会"],
    "购物": ["日常购物", "逛街休闲", "买礼物", "家庭采购", "节日购物"],
    "运动健身": ["日常锻炼", "减脂塑形", "增肌训练", "放松身心", "学习技能"],
    "亲子": ["亲子活动", "周末遛娃", "生日派对", "假期活动", "学习体验"],
}

# ============================================================
# 生成函数
# ============================================================


def weighted_choice(categories_dict):
    """按权重选择类别"""
    total = sum(v["weight"] for v in categories_dict.values())
    r = random.uniform(0, total)
    cumulative = 0
    for cat, info in categories_dict.items():
        cumulative += info["weight"]
        if r <= cumulative:
            return cat
    return list(categories_dict.keys())[0]


def generate_coordinate(center, spread=0.03):
    """生成以城市中心为基准的随机坐标"""
    lon = center[0] + random.uniform(-spread, spread)
    lat = center[1] + random.uniform(-spread, spread)
    return round(lon, 6), round(lat, 6)


def generate_phone():
    """生成随机手机号"""
    prefixes = ["130", "131", "132", "133", "134", "135", "136", "137", "138", "139",
                 "150", "151", "152", "153", "155", "156", "157", "158", "159",
                 "170", "171", "172", "173", "175", "176", "177", "178",
                 "180", "181", "182", "183", "184", "185", "186", "187", "188", "189"]
    return random.choice(prefixes) + "".join([str(random.randint(0, 9)) for _ in range(8)])


def generate_poi_name(category, subcategory):
    """根据类别生成POI名称"""
    if category == "餐饮":
        if "火锅" in subcategory:
            prefix = random.choice(RESTAURANT_PREFIXES + RESTAURANT_MIDS)
            suffix = random.choice(RESTAURANT_SUFFIXES_HOTPOT)
            return f"{prefix}{suffix}"
        elif "烧烤" in subcategory:
            prefix = random.choice(RESTAURANT_PREFIXES + RESTAURANT_MIDS)
            suffix = random.choice(RESTAURANT_SUFFIXES_BBQ)
            return f"{prefix}{suffix}"
        elif any(x in subcategory for x in ["咖啡", "甜品", "饮品", "茶"]):
            prefix = random.choice(RESTAURANT_PREFIXES + RESTAURANT_MIDS + ADJECTIVES)
            suffix = random.choice(RESTAURANT_SUFFIXES_CAFE)
            return f"{prefix}{suffix}"
        elif any(x in subcategory for x in ["小吃", "面", "粉", "快餐"]):
            prefix = random.choice(RESTAURANT_PREFIXES + RESTAURANT_MIDS)
            suffix = random.choice(RESTAURANT_SUFFIXES_SNACK)
            return f"{prefix}{suffix}"
        else:
            prefix = random.choice(RESTAURANT_PREFIXES + RESTAURANT_MIDS)
            suffix = random.choice(RESTAURANT_SUFFIXES_RESTAURANT)
            return f"{prefix}{suffix}"
    elif category == "景点":
        prefix = random.choice(ATTRACTION_PREFIXES)
        suffix = random.choice(ATTRACTION_TYPES)
        return f"{prefix}{suffix}"
    elif category == "娱乐":
        prefix = random.choice(ENTERTAINMENT_PREFIXES)
        return f"{prefix}{subcategory}"
    elif category == "文化":
        prefix = random.choice(ADJECTIVES + ["新", "旧", "古", "今", "雅", "韵", "墨", "书", "艺", "文"])
        return f"{prefix}{subcategory}"
    elif category == "购物":
        prefix = random.choice(["万达", "银泰", "大悦城", "华润", "龙湖", "中粮", "凯德", "恒隆", "太古", "新世界", "百联", "天虹", "茂业", "金鹰", "来福士", "印象城", "吾悦", "宝龙", "融创", "新城"])
        return f"{prefix}{random.choice(['广场', '中心', 'mall', '荟', '天地'])}"
    elif category == "运动健身":
        prefix = random.choice(["活力", "动感", "极速", "飞扬", "超越", "巅峰", "精英", "冠军", "力量", "速度", "耐力", "爆发", "热血", "激情", "阳光", "青春"])
        return f"{prefix}{subcategory}"
    elif category == "亲子":
        prefix = random.choice(["小天才", "快乐宝贝", "童趣", "乐高", "梦幻", "奇妙", "开心果", "小星星", "月亮船", "彩虹桥", "太阳花", "向日葵", "小蜜蜂", "蝴蝶谷", "米奇", "迪士尼"])
        return f"{prefix}{subcategory}"
    return f"{random.choice(ADJECTIVES)}{subcategory}"


def generate_description(name, city, district, street, category, subcategory, tags):
    """生成POI描述"""
    templates = DESCRIPTION_TEMPLATES.get(category, DESCRIPTION_TEMPLATES["景点"])
    template = random.choice(templates)
    adj = random.choice(ADJECTIVES)
    tag_str = "、".join(random.sample(tags, min(3, len(tags))))
    scene = random.choice(SCENES.get(category, ["休闲"]))
    return template.format(
        name=name, city=city, district=district, street=street,
        subcategory=subcategory, adj=adj, tag=tag_str, scene=scene
    )


def generate_features(category):
    """根据类别生成 features 特征向量"""
    bias = FEATURES_BIAS.get(category, FEATURES_BIAS["景点"])
    features = {}
    for key, (lo, hi) in bias.items():
        val = random.uniform(lo, hi)
        features[key] = round(min(1.0, max(0.0, val)), 2)
    return features


def generate_poi(poi_id, cities, categories):
    """生成单条POI数据"""
    city_name = random.choice(list(cities.keys()))
    city_info = cities[city_name]
    district = random.choice(city_info["districts"])

    category = weighted_choice(categories)
    cat_info = categories[category]
    subcategory = random.choice(cat_info["subcategories"])

    lon, lat = generate_coordinate(city_info["center"])

    name = generate_poi_name(category, subcategory)

    street = random.choice(STREET_NAMES)
    street_num = random.randint(1, 999)
    address = f"{city_name}{district}{street}{street_num}号"

    base_rating = cat_info["rating_bias"]
    rating = round(min(5.0, max(1.0, random.gauss(base_rating, 0.5))), 1)

    cost_min, cost_max = cat_info["avg_cost_range"]
    price = round(random.uniform(cost_min, cost_max), 0)

    q_min, q_max = cat_info["queue_range"]

    opening_hours = random.choice(OPENING_HOURS_TEMPLATES)
    if "-" in opening_hours:
        parts = opening_hours.split("-")
        open_time = parts[0]
        close_time = parts[1]
    else:
        open_time = "00:00"
        close_time = "23:59"

    avg_stay_minutes = random.randint(20, 180)

    available_tags = TAGS_BY_CATEGORY.get(category, ["热门"])
    tags = random.sample(available_tags, min(random.randint(2, 5), len(available_tags)))

    description = generate_description(name, city_name, district, street, category, subcategory, tags)

    image_count = random.randint(1, 9)
    images = [f"https://pics.example.com/poi/{poi_id}_{i}.jpg" for i in range(image_count)]

    features = generate_features(category)

    category_en = CATEGORY_EN_MAP.get(category, "attraction")
    sub_category_en = SUBCATEGORY_EN_MAP.get(category, {}).get(subcategory, subcategory)

    return {
        "id": f"gen_{poi_id:07d}",
        "name": name,
        "category": category_en,
        "sub_category": sub_category_en,
        "city": city_name,
        "lat": lat,
        "lng": lon,
        "address": address,
        "rating": rating,
        "price": int(price),
        "open_time": open_time,
        "close_time": close_time,
        "avg_stay_minutes": avg_stay_minutes,
        "tags": tags,
        "features": features,
        "district": district,
        "description": description,
        "images": images,
        "created_at": f"2024-{random.randint(1,12):02d}-{random.randint(1,28):02d}",
        "updated_at": f"2025-{random.randint(1,12):02d}-{random.randint(1,28):02d}",
    }


REVIEW_TEMPLATES = {
    "food": {
        "positive": [
            "{adj}的味道，{feature}，下次还会来。",
            "菜品{adj}，{feature}，朋友们都说好。",
            "第一次来就被{feature}吸引，味道{adj}，推荐{dish}。",
            "{dish}做得很{adj}，{feature}，聚餐首选。",
            "性价比很高，{feature}，{dish}必点。",
        ],
        "neutral": [
            "味道还行，{feature}，不过{neg}。",
            "整体中规中矩，{feature}，{neg}。",
            "{dish}还可以，{neg}，但{feature}。",
            "适合随便吃吃，{neg}，{feature}倒是不错。",
        ],
        "negative": [
            "味道一般，{neg}，不太推荐。",
            "{dish}做得不好，{neg}，不会再来。",
            "等了好久，{neg}，体验很差。",
        ],
    },
    "attraction": {
        "positive": [
            "景色{adj}，{feature}，很适合拍照。",
            "环境{adj}，{feature}，值得一来。",
            "空气清新，{feature}，周末来放松很舒服。",
            "{feature}，{adj}的感觉，带家人来也很合适。",
            "比想象中好，{feature}，下次带朋友来。",
        ],
        "neutral": [
            "还行吧，{feature}，但{neg}。",
            "景色不错，{neg}，适合短暂停留。",
            "一般般，{feature}，{neg}。",
        ],
        "negative": [
            "人太多了，{neg}，体验不好。",
            "和预期差距大，{neg}，不推荐。",
            "门票不值，{neg}，不会再来。",
        ],
    },
    "entertainment": {
        "positive": [
            "玩得很开心，{feature}，强烈推荐。",
            "设施{adj}，{feature}，下次还来。",
            "朋友聚会首选，{feature}，气氛很好。",
            "{feature}，项目丰富，{adj}的体验。",
        ],
        "neutral": [
            "还可以，{feature}，但{neg}。",
            "项目一般，{neg}，{feature}倒是不错。",
            "适合打发时间，{neg}。",
        ],
        "negative": [
            "设备旧了，{neg}，体验不好。",
            "性价比低，{neg}，不推荐。",
        ],
    },
    "culture": {
        "positive": [
            "氛围{adj}，{feature}，很适合安静地待一下午。",
            "展览{adj}，{feature}，学到了很多。",
            "{feature}，文化气息浓厚，{adj}的空间。",
            "很文艺，{feature}，适合拍照打卡。",
        ],
        "neutral": [
            "还行，{feature}，但{neg}。",
            "展览一般，{neg}，环境倒是不错。",
        ],
        "negative": [
            "展品少，{neg}，不值得专门来。",
        ],
    },
    "shopping": {
        "positive": [
            "品牌齐全，{feature}，逛得很过瘾。",
            "环境{adj}，{feature}，购物体验好。",
            "{feature}，{adj}的商场，一站式搞定。",
        ],
        "neutral": [
            "还行吧，{feature}，但{neg}。",
            "品牌一般，{neg}，顺便逛逛可以。",
        ],
        "negative": [
            "东西贵，{neg}，不太推荐。",
        ],
    },
    "fitness": {
        "positive": [
            "器材齐全，{feature}，锻炼体验很好。",
            "环境{adj}，{feature}，教练专业。",
            "{feature}，场地{adj}，运动首选。",
        ],
        "neutral": [
            "还行，{feature}，但{neg}。",
        ],
        "negative": [
            "设备老旧，{neg}，不推荐。",
        ],
    },
    "family": {
        "positive": [
            "孩子玩得很开心，{feature}，安全放心。",
            "项目{adj}，{feature}，亲子活动首选。",
            "{feature}，{adj}的环境，适合带娃。",
        ],
        "neutral": [
            "还可以，{feature}，但{neg}。",
        ],
        "negative": [
            "人太多，{neg}，孩子容易走散。",
        ],
    },
}

POSITIVE_FEATURES = [
    "服务态度好", "环境优雅", "氛围感强", "拍照出片", "人少清净",
    "交通方便", "排队时间短", "性价比高", "分量十足", "食材新鲜",
    "空调给力", "停车方便", "有WiFi", "装修精致", "灯光很好",
]
NEGATIVE_FEATURES = [
    "排队太久了", "人太多了", "环境嘈杂", "价格偏高", "服务态度一般",
    "停车不方便", "空间太小", "味道一般", "位置偏僻", "卫生一般",
    "等位时间长", "空调不够", "隔音差", "光线不好",
]
POSITIVE_ADJ = ["好吃", "舒服", "漂亮", "精致", "安静", "丰富", "地道", "惊艳", "舒适", "棒"]
NEGATIVE_ADJ = ["一般", "普通", "失望", "差强人意", "不太行"]
DISH_WORDS = ["招牌菜", "特色菜", "主菜", "甜品", "饮品", "小吃", "锅底", "汤底", "甜点"]


def generate_review(review_id, poi, user_id):
    category = poi["category"]
    rating = poi["rating"]
    if rating >= 4.0:
        weights = [0.7, 0.25, 0.05]
    elif rating >= 3.0:
        weights = [0.3, 0.5, 0.2]
    else:
        weights = [0.1, 0.3, 0.6]
    sentiment = random.choices(["positive", "neutral", "negative"], weights=weights, k=1)[0]

    cat_templates = REVIEW_TEMPLATES.get(category, REVIEW_TEMPLATES["attraction"])
    template = random.choice(cat_templates[sentiment])

    if sentiment == "positive":
        feature = random.choice(POSITIVE_FEATURES)
        adj = random.choice(POSITIVE_ADJ)
    elif sentiment == "negative":
        feature = random.choice(NEGATIVE_FEATURES)
        adj = random.choice(NEGATIVE_ADJ)
    else:
        feature = random.choice(POSITIVE_FEATURES)
        adj = random.choice(POSITIVE_ADJ + NEGATIVE_ADJ)

    neg = random.choice(NEGATIVE_FEATURES)
    dish = random.choice(DISH_WORDS)

    text = template.format(feature=feature, adj=adj, neg=neg, dish=dish)

    available_tags = TAGS_BY_CATEGORY.get("餐饮" if category == "food" else "景点" if category == "attraction" else "娱乐" if category == "entertainment" else "文化" if category == "culture" else "购物" if category == "shopping" else "运动健身" if category == "fitness" else "亲子", ["热门"])
    review_tags = random.sample(available_tags, min(random.randint(1, 3), len(available_tags)))

    review_rating_offset = random.uniform(-0.5, 0.5)
    review_rating = round(min(5.0, max(1.0, rating + review_rating_offset)), 1)

    month = random.randint(1, 12)
    day = random.randint(1, 28)
    created_at = f"2025-{month:02d}-{day:02d}"

    return {
        "id": f"r{review_id:07d}",
        "poi_id": poi["id"],
        "user_id": user_id,
        "rating": review_rating,
        "sentiment": sentiment,
        "text": text,
        "tags": review_tags,
        "created_at": created_at,
    }


def generate_reviews_for_pois(all_pois, reviews_per_poi_range=(1, 8)):
    all_reviews = []
    review_id = 0
    for poi in all_pois:
        count = random.randint(*reviews_per_poi_range)
        for _ in range(count):
            uid = f"u{random.randint(1, 50000):05d}"
            all_reviews.append(generate_review(review_id, poi, uid))
            review_id += 1
    return all_reviews


def write_csv(data, filepath):
    """写入CSV文件"""
    if not data:
        return
    fieldnames = data[0].keys()
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in data:
            # 将列表和字典转为JSON字符串
            row_copy = {}
            for k, v in row.items():
                if isinstance(v, (list, dict)):
                    row_copy[k] = json.dumps(v, ensure_ascii=False)
                else:
                    row_copy[k] = v
            writer.writerow(row_copy)


def write_json(data, filepath):
    """写入JSON文件"""
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    total = 100000
    base_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.join(base_dir, "data")
    os.makedirs(output_dir, exist_ok=True)
    csv_path = os.path.join(output_dir, "poi_data_100k.csv")
    json_path = os.path.join(output_dir, "poi_data_100k.json")

    print(f"开始生成 {total:,} 条POI数据...")
    print(f"输出目录: {output_dir}")
    print("-" * 60)

    start_time = time.time()

    all_pois = []
    batch_size = 10000
    for batch_start in range(0, total, batch_size):
        batch_end = min(batch_start + batch_size, total)
        batch = []
        for i in range(batch_start, batch_end):
            batch.append(generate_poi(i, CITIES, CATEGORIES))
        all_pois.extend(batch)
        elapsed = time.time() - start_time
        progress = batch_end / total * 100
        print(f"  进度: {batch_end:>7,}/{total:,} ({progress:5.1f}%) | 耗时: {elapsed:.1f}s")

    gen_time = time.time() - start_time
    print("-" * 60)
    print(f"数据生成完成! 耗时: {gen_time:.1f}s")

    # 写入CSV
    print(f"\n正在写入CSV文件...")
    t = time.time()
    write_csv(all_pois, csv_path)
    csv_size = os.path.getsize(csv_path) / (1024 * 1024)
    print(f"  CSV写入完成: {csv_path} ({csv_size:.1f} MB, 耗时 {time.time()-t:.1f}s)")

    # 写入JSON
    print(f"\n正在写入JSON文件...")
    t = time.time()
    write_json(all_pois, json_path)
    json_size = os.path.getsize(json_path) / (1024 * 1024)
    print(f"  JSON写入完成: {json_path} ({json_size:.1f} MB, 耗时 {time.time()-t:.1f}s)")

    reviews_csv_path = os.path.join(output_dir, "reviews_100k.csv")
    reviews_json_path = os.path.join(output_dir, "reviews_100k.json")

    print(f"\n正在为每个POI生成用户评论 (每个POI 1~8 条)...")
    t = time.time()
    all_reviews = generate_reviews_for_pois(all_pois)
    print(f"  评论生成完成: {len(all_reviews):,} 条, 耗时 {time.time()-t:.1f}s")

    print(f"\n正在写入评论CSV文件...")
    t = time.time()
    write_csv(all_reviews, reviews_csv_path)
    rcsv_size = os.path.getsize(reviews_csv_path) / (1024 * 1024)
    print(f"  CSV写入完成: {reviews_csv_path} ({rcsv_size:.1f} MB, 耗时 {time.time()-t:.1f}s)")

    print(f"\n正在写入评论JSON文件...")
    t = time.time()
    write_json(all_reviews, reviews_json_path)
    rjson_size = os.path.getsize(reviews_json_path) / (1024 * 1024)
    print(f"  JSON写入完成: {reviews_json_path} ({rjson_size:.1f} MB, 耗时 {time.time()-t:.1f}s)")

    # 统计信息
    print("\n" + "=" * 60)
    print("数据统计:")
    print("=" * 60)

    # 城市分布
    city_counts = {}
    cat_counts = {}
    for poi in all_pois:
        city_counts[poi["city"]] = city_counts.get(poi["city"], 0) + 1
        cat_counts[poi["category"]] = cat_counts.get(poi["category"], 0) + 1

    print(f"\n城市分布 (Top 10):")
    for city, count in sorted(city_counts.items(), key=lambda x: -x[1])[:10]:
        print(f"  {city}: {count:>6,} ({count/total*100:.1f}%)")

    print(f"\n类别分布:")
    for cat, count in sorted(cat_counts.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count:>6,} ({count/total*100:.1f}%)")

    # 评分统计
    ratings = [p["rating"] for p in all_pois]
    avg_rating = sum(ratings) / len(ratings)
    print(f"\n评分统计:")
    print(f"  平均评分: {avg_rating:.2f}")
    print(f"  最低评分: {min(ratings)}")
    print(f"  最高评分: {max(ratings)}")

    # 消费统计
    costs = [p["price"] for p in all_pois]
    avg_cost = sum(costs) / len(costs)
    print(f"\n消费统计:")
    print(f"  平均人均消费: ¥{avg_cost:.0f}")
    print(f"  最低人均消费: ¥{min(costs):.0f}")
    print(f"  最高人均消费: ¥{max(costs):.0f}")

    sentiment_counts = {}
    for r in all_reviews:
        sentiment_counts[r["sentiment"]] = sentiment_counts.get(r["sentiment"], 0) + 1
    print(f"\n评论统计:")
    print(f"  总评论数: {len(all_reviews):,}")
    print(f"  平均每个POI: {len(all_reviews)/total:.1f} 条")
    for s, c in sorted(sentiment_counts.items(), key=lambda x: -x[1]):
        print(f"  {s}: {c:,} ({c/len(all_reviews)*100:.1f}%)")

    total_time = time.time() - start_time
    print(f"\n总耗时: {total_time:.1f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
