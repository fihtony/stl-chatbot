"""中学专用术语映射，用于英语到法语的查询翻译。"""

# 中学专用术语映射（针对 Collège Saint-Louis 知识库）
SECONDARY_SCHOOL_TERMS = {
    # ========== 学校管理 ==========
    "principal": ["directeur", "directrice", "chef d'établissement"],
    "vice principal": ["directeur adjoint", "directrice adjointe"],
    "school board": ["conseil d'établissement", "commission scolaire"],
    "administration": ["direction", "administration"],
    "secretary": ["secrétaire", "réceptionniste"],
    # ========== 时间/日程 ==========
    "opening hours": ["heures d'ouverture", "horaire d'ouverture"],
    "school hours": ["heures de classe", "horaire scolaire"],
    "schedule": ["horaire", "calendrier", "emploi du temps"],
    "timetable": ["horaire", "emploi du temps", "planning"],
    "exam schedule": ["horaire des examens", "calendrier des examens"],
    "lunch hour": ["heure du dîner", "période du dîner"],
    # ========== 年级（中学特定：1re-5e secondaire）==========
    "grade 1": ["1re secondaire", "1ère secondaire", "1er cycle"],
    "grade 2": ["2e secondaire", "1er cycle"],
    "grade 3": ["3e secondaire", "2e cycle"],
    "grade 4": ["4e secondaire", "2e cycle"],
    "grade 5": ["5e secondaire", "2e cycle"],
    "first cycle": ["1er cycle", "1re-2e secondaire"],
    "second cycle": ["2e cycle", "3e-4e-5e secondaire"],
    "secondary 1": ["1re secondaire"],
    "secondary 2": ["2e secondaire"],
    "secondary 3": ["3e secondaire"],
    "secondary 4": ["4e secondaire"],
    "secondary 5": ["5e secondaire"],
    # ========== 设施 ==========
    "library": ["bibliothèque", "médiathèque", "centre de ressources"],
    "cafeteria": ["cafétéria", "cantine", "service alimentaire"],
    "gym": ["gymnase", "salle de sport"],
    "locker": ["caserne", "casier"],
    "classroom": ["classe", "salle de classe", "local"],
    "lab": ["laboratoire", "lab"],
    # ========== 活动/事件 ==========
    "open house": ["portes ouvertes", "journée portes ouvertes", "visite"],
    "parent teacher meeting": ["meeting parents", "réunion parents"],
    "field trip": ["sortie scolaire", "excursion", "sortie éducative"],
    "school dance": ["bal", "activité sociale"],
    "spirit day": ["journée d'esprit", "journée thématique"],
    # ========== 课程/科目 ==========
    "math": ["mathématiques", "maths"],
    "mathematics": ["mathématiques"],
    "english": ["anglais"],
    "french": ["français"],
    "science": ["sciences"],
    "history": ["histoire"],
    "geography": ["géographie"],
    "physical education": ["éducation physique", "éduc physique", "gym"],
    "arts": ["arts", "art dramatique", "arts plastiques"],
    # ========== 学生服务 ==========
    "guidance counselor": ["conseiller d'orientation", "orientation"],
    "tutoring": ["tutorat", "récupération", "aide aux devoirs"],
    "homework help": ["aide aux devoirs", "tutorat"],
    "bullying": ["intimidation", "harcèlement"],
    "busing": ["transport scolaire", "autobus", "transport"],
    "lockdown": ["confinement", "procédure d'urgence"],
}


def get_french_translations(english_term: str) -> list[str]:
    """获取英语术语的法语翻译列表。"""
    return ENGLISH_TO_FRENCH_TERMS.get(english_term.lower(), [])


# 法语查询的术语扩展映射（同义词变体）
FRENCH_TERM_EXPANSIONS = {
    "directeur": [
        "directrice",
        "chef d'établissement",
        "direction",
        "principal",
        "proviseur",
    ],
    "directrice": [
        "directeur",
        "chef d'établissement",
        "direction",
        "principal",
        "proviseur",
    ],
    "principal": [
        "directeur",
        "directrice",
        "chef d'établissement",
        "proviseur",
    ],  # 英语loanword需要映射到directeur
    "proviseur": [
        "directeur",
        "directrice",
        "chef d'établissement",
        "principal",
    ],  # 另一个表示校长的词
    "collège": ["école", "établissement", "secondaire"],
    "école": ["collège", "établissement"],
    "mission": ["vision", "objectif", "valeurs"],
    # 位置/联系相关
    "adresse": ["nous joindre", "localisation", "où est", "où se trouve", "contact"],
    "où est": ["adresse", "localisation", "nous joindre", "où se trouve"],
}

# 英语术语到法语的映射（用于翻译）
ENGLISH_TO_FRENCH_TERMS = {
    # ========== 学校管理 ==========
    "principal": ["directeur", "directrice", "chef d'établissement"],
    "vice principal": ["directeur adjoint", "directrice adjointe"],
    "school board": ["conseil d'établissement", "commission scolaire"],
    "administration": ["direction", "administration"],
    "secretary": ["secrétaire", "réceptionniste"],
    # ========== 时间/日程 ==========
    "opening hours": ["heures d'ouverture", "horaire d'ouverture"],
    "school hours": ["heures de classe", "horaire scolaire"],
    "schedule": ["horaire", "calendrier", "emploi du temps"],
    "timetable": ["horaire", "emploi du temps", "planning"],
    # ========== 年级（中学特定：1re-5e secondaire）==========
    "grade 1": ["1re secondaire", "1ère secondaire", "1er cycle"],
    "grade 2": ["2e secondaire", "1er cycle"],
    "grade 3": ["3e secondaire", "2e cycle"],
    "grade 4": ["4e secondaire", "2e cycle"],
    "grade 5": ["5e secondaire", "2e cycle"],
    "secondary 1": ["1re secondaire", "1er cycle"],
    "secondary 2": ["2e secondaire", "1er cycle"],
    "secondary 3": ["3e secondaire", "2e cycle"],
    "secondary 4": ["4e secondaire", "2e cycle"],
    "secondary 5": ["5e secondaire", "2e cycle"],
    "first cycle": ["1er cycle", "1re-2e secondaire"],
    "second cycle": ["2e cycle", "3e-4e-5e secondaire"],
    # ========== 设施 ==========
    "library": ["bibliothèque", "médiathèque", "centre de ressources"],
    "cafeteria": ["cafétéria", "cantine", "service alimentaire"],
    "gym": ["gymnase", "salle de de sport"],
    # ========== 活动/事件 ==========
    "open house": ["portes ouvertes", "journée portes ouvertes", "visite"],
    "field trip": ["sortie scolaire", "excursion", "sortie éducative"],
    # ========== 科目 ==========
    "science": ["sciences"],
    "history": ["histoire"],
    "geography": ["géographie"],
    "math": ["mathématiques", "maths"],
    "mathematics": ["mathématiques"],
    # ========== 位置/联系 ==========
    "address": ["adresse", "nous joindre", "localisation", "où est", "où se trouve"],
    "location": ["adresse", "endroit", "place", "nous joindre"],
    "where is": ["où est", "où se trouve", "localisation", "adresse"],
}


def expand_query_with_school_terms(query: str, lang: str = "en") -> list[str]:
    """
    使用中学术语映射扩展查询。

    支持英语和法语查询的术语扩展。

    Args:
        query: 原始查询
        lang: 查询语言 (en, fr, zh)

    Returns:
        扩展后的查询列表（包含原查询）
    """
    queries = [query]
    query_lower = query.lower()

    # 英语查询：使用英语到法语的术语映射
    if lang == "en":
        # 查找并替换学校术语
        for en_term, fr_terms in ENGLISH_TO_FRENCH_TERMS.items():
            if en_term in query_lower:
                for fr_term in fr_terms[:2]:  # 最多取2个法语变体
                    expanded = query_lower.replace(en_term, fr_term)
                    if expanded != query_lower:
                        queries.append(expanded)
        return queries

    # 法语查询：使用法语同义词扩展
    if lang == "fr":
        # 移除特殊字符以便匹配
        query_normalized = (
            query_lower.replace("'", "").replace("'", "").replace("?", "")
        )

        for term, synonyms in FRENCH_TERM_EXPANSIONS.items():
            if term in query_normalized:
                for synonym in synonyms:
                    # 创建扩展查询（保持原始大小写风格）
                    if synonym != term:
                        expanded = query_lower.replace(term, synonym)
                        if expanded != query_lower and expanded not in [
                            q.lower() for q in queries
                        ]:
                            queries.append(expanded)
        return queries

    # 中文或其他语言：不扩展
    return queries
