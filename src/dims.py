"""维度体系（taxonomy）与错误分类学（error taxonomy）公共定义。

错误分类学用于"陷阱题"：所有选项都有失误，只有权重高低之分。
"""
DIMENSIONS = [
    {"name": "说话之道", "desc": "委婉表达、话里有话、点到为止、听弦外之音、不当面驳人"},
    {"name": "饭局礼仪", "desc": "座次排序、敬酒劝酒、谁来买单、点菜分寸、照顾在座人员"},
    {"name": "面子文化", "desc": "给面子、留面子、驳面子的代价、打圆场、台阶"},
    {"name": "职场潜规则", "desc": "功高盖主、不当面评价同事、背锅、抢功、汇报分寸、与领导相处"},
    {"name": "人情往来", "desc": "欠人情、还人情、礼尚往来、随份子、请客还局的节奏"},
    {"name": "拒绝的艺术", "desc": "怎么拒绝才不得罪人、委婉推辞、扮丑/示弱式拒绝"},
    {"name": "分寸与边界", "desc": "交浅言深、客套话vs真邀请、刚认识的分寸、关系亲疏"},
    {"name": "家庭关系", "desc": "婆媳、亲戚往来、辈分称呼、家族聚会、彩礼嫁妆"},
    {"name": "敏感话题", "desc": "工资、年龄、收入、婚育、外貌身材的回避与转移技巧"},
    {"name": "危机化解", "desc": "误会、冲突、尴尬场面、说错话后的补救圆场"},
]

# ---- 错误分类学：人情世故失误的轻重等级 ----
# weight 越大越严重。陷阱题中每个选项可携带多个错误类型，扣分=各 weight 之和。
ERRORS = [
    {"code": "E1", "name": "当众驳他人面子", "weight": 10,
     "desc": "公开指出他人错误、让领导下不来台、当众拆穿"}, 
    {"code": "E2", "name": "泄露敏感信息", "weight": 9,
     "desc": "主动问/答工资、收入、年龄、婚育、他人隐私"},
    {"code": "E3", "name": "得罪实权人物", "weight": 8,
     "desc": "无视上级权威、公开拒绝领导、在领导面前抢功"},
    {"code": "E4", "name": "当面评价他人", "weight": 7,
     "desc": "在有第三方的场合评价同事能力/人品，落人口实"},
    {"code": "E5", "name": "承诺无法兑现", "weight": 6,
     "desc": "满口答应却做不到，透支信用"},
    {"code": "E6", "name": "交浅言深/越界", "weight": 6,
     "desc": "对不熟的人掏心窝或替人做主、过度关心"},
    {"code": "E7", "name": "拒绝生硬无缓冲", "weight": 5,
     "desc": "不留余地直接说不，不给对方台阶"},
    {"code": "E8", "name": "油滑空洞不可信", "weight": 4,
     "desc": "满口大道理、永远打太极、敷衍应付"},
    {"code": "E9", "name": "逃避责任无担当", "weight": 4,
     "desc": "遇事推诿、甩锅、不背自己该背的锅"},
    {"code": "E10", "name": "小失误", "weight": 2,
     "desc": "称呼错误、忘带东西、迟到的应酬细节"},
]

ERROR_MAP = {e["code"]: e for e in ERRORS}
ERROR_WEIGHT = {e["code"]: e["weight"] for e in ERRORS}

# 陷阱题最高失误分（用于把加权失误归一化为 0-100 得分）
# 一个选项最多允许 3 个错误，理论最大失误 = 10+9+8 = 27
TRAP_MAX_PENALTY = 30


def penalty_of(errors: list) -> int:
    """计算选项的失误罚分（多个错误累计）。"""
    return sum(ERROR_WEIGHT.get(e.get("code"), 0) for e in errors)


if __name__ == "__main__":
    print("错误分类学权重一览：")
    for e in sorted(ERRORS, key=lambda x: -x["weight"]):
        print(f"  {e['code']} {e['name']:<12} -{e['weight']}")