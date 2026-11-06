#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RoboMemory · 可嵌入任意机器人的长期记忆模块

给别人的机器人用，只要三行：

    from robomemory import Memory
    mem = Memory("memory.db")
    mem.remember("我怕黑，晚上别关灯")
    print(mem.recall("今晚有点暗"))

零依赖，只用 Python 标准库。
"""

import re
import sqlite3
import datetime

# 偏好类关键词：说明"用户喜欢/讨厌什么"
PREF_WORDS = ["我怕", "我害怕", "我不敢", "我不喜欢", "我讨厌", "我习惯", "我喜欢", "我受不了"]
# 情景类关键词：说明"发生过什么"
EPI_WORDS = ["上次", "刚才", "昨天", "前天", "失败", "摔了", "打滑", "没成功"]


def _bigrams(s):
    """把句子切成两字一组的碎片，用来算重合度。
    中文不用分词也能用，胜在零依赖。"""
    s = re.sub(r"\s+", "", s)
    return {s[i:i + 2] for i in range(len(s) - 1)}


class Memory:
    """一个记忆库 = 一个 sqlite 文件。

    换机器人、换身体、换机器，把这个文件拷过去，记忆就跟着走。
    """

    def __init__(self, path="memory.db"):
        self.path = str(path)
        self._init_db()

    # ---------------------------------------------------------- 建表
    def _init_db(self):
        c = sqlite3.connect(self.path)
        c.execute("""CREATE TABLE IF NOT EXISTS memories(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            content TEXT NOT NULL,
            confidence REAL DEFAULT 0.6,
            created_at TEXT NOT NULL
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS meta(
            key TEXT PRIMARY KEY, value TEXT
        )""")
        c.commit()
        c.close()

    def _conn(self):
        return sqlite3.connect(self.path)

    # ---------------------------------------------------------- 抽取
    @staticmethod
    def extract(text):
        """把一段话拆成若干条记忆，返回 [(kind, content, confidence), ...]

        规则版，不调用模型。想换成大模型抽取，只改这一个方法。
        """
        out = []
        for s in re.split(r"[。！？!?；;\n]", text or ""):
            s = s.strip()
            if len(s) < 3:
                continue
            if any(k in s for k in PREF_WORDS):
                out.append(("preference", s, 0.85))
            elif any(k in s for k in EPI_WORDS):
                out.append(("episode", s, 0.75))
            elif "我" in s and len(s) >= 4:
                out.append(("fact", s, 0.6))
        return out

    # ---------------------------------------------------------- 写
    def remember(self, text):
        """从一段话里抽取并存入。返回写入条数。"""
        items = self.extract(text)
        if not items:
            return 0
        now = datetime.datetime.now().isoformat(timespec="seconds")
        c = self._conn()
        c.executemany(
            "INSERT INTO memories(kind,content,confidence,created_at) VALUES(?,?,?,?)",
            [(k, v, f, now) for k, v, f in items],
        )
        c.commit()
        c.close()
        return len(items)

    def add(self, kind, content, confidence=0.8):
        """直接写一条，不走抽取。适合传感器事件、任务结果。"""
        now = datetime.datetime.now().isoformat(timespec="seconds")
        c = self._conn()
        c.execute(
            "INSERT INTO memories(kind,content,confidence,created_at) VALUES(?,?,?,?)",
            (kind, content, confidence, now),
        )
        c.commit()
        c.close()
        return 1

    # ---------------------------------------------------------- 读
    def recall(self, query, k=3):
        """找出和 query 最相关的 k 条。返回 [{'id','kind','content','score'}, ...]

        打分 = 字面重合 × 0.75 + 新旧程度 × 0.25
        先比两字词（准），没有词命中再退到单字（宽），这样换个说法也能想起来。
        """
        rows = self.all()
        if not rows:
            return []
        q_bigram = _bigrams(query)
        q_chars = set(re.sub(r"\s+", "", query or ""))
        if not q_chars:
            return []
        now = datetime.datetime.now()
        scored = []
        for r in rows:
            content = r["content"]
            m_bigram = _bigrams(content)
            inter = len(q_bigram & m_bigram)
            by_bigram = inter / (len(q_bigram) + 1)
            m_chars = set(re.sub(r"\s+", "", content))
            by_char = len(q_chars & m_chars) / (len(q_chars) + 1) * 0.5
            base = max(by_bigram, by_char)
            if base <= 0:
                continue  # 一个字都对不上，说明没关系，别硬凑
            try:
                age = (now - datetime.datetime.fromisoformat(r["created_at"])).days
            except Exception:
                age = 0
            recency = 1.0 / (1 + max(age, 0) * 0.15)
            score = base * 0.75 + recency * 0.25 * (r["confidence"] or 0.6)
            if score > 0.08:
                scored.append({**r, "score": round(score, 3)})
        scored.sort(key=lambda x: (x["score"], x["id"]), reverse=True)
        return scored[:k]

    def all(self):
        """按时间顺序返回全部记忆。"""
        c = self._conn()
        rows = c.execute(
            "SELECT id,kind,content,confidence,created_at FROM memories ORDER BY id"
        ).fetchall()
        c.close()
        return [
            {"id": r[0], "kind": r[1], "content": r[2], "confidence": r[3], "created_at": r[4]}
            for r in rows
        ]

    def count(self):
        return len(self.all())

    # ---------------------------------------------------------- 删
    def forget_one(self, mid):
        """删掉一条。用户有权让机器人忘掉某一件事。"""
        c = self._conn()
        c.execute("DELETE FROM memories WHERE id=?", (mid,))
        c.commit()
        n = c.total_changes
        c.close()
        return n

    def forget(self):
        """删掉全部记忆。"""
        n = self.count()
        c = self._conn()
        c.execute("DELETE FROM memories")
        c.commit()
        c.close()
        return n

    # ---------------------------------------------------------- 杂项状态
    def set_meta(self, key, value):
        c = self._conn()
        c.execute("INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)", (key, str(value)))
        c.commit()
        c.close()

    def get_meta(self, key, default=None):
        c = self._conn()
        row = c.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        c.close()
        return row[0] if row else default


if __name__ == "__main__":
    # 这个文件是「库」，不是程序 —— 直接双击运行不会启动聊天，
    # 但会跑一个自检，让你看见它到底能干什么。
    import os
    import tempfile

    print("=" * 56)
    print("RoboMemory 自检")
    print("说明：robomemory.py 是一个库，给别人的机器人用。")
    print("      想聊天请运行 memory_bot.py。下面演示库的能力。")
    print("=" * 56)

    tmp = os.path.join(tempfile.gettempdir(), "_robomemory_selftest.db")
    if os.path.exists(tmp):
        os.remove(tmp)

    mem = Memory(tmp)
    mem.remember("我怕黑，晚上别关灯。上次搬杯子摔了，夹爪打滑。")
    mem.add("skill", "拿杯子要先降 2cm 再闭合", 0.9)

    print(f"\n写入 {mem.count()} 条记忆：")
    for r in mem.all():
        print(f"  #{r['id']}  [{r['kind']}]  {r['content']}")

    print("\n查「今晚有点暗」：")
    for r in mem.recall("今晚有点暗", 2):
        print(f"  {r['score']:.3f}  {r['content']}")

    print("\n查「杯子怎么拿」：")
    for r in mem.recall("杯子怎么拿", 2):
        print(f"  {r['score']:.3f}  {r['content']}")

    print("\n查「明天天气」：", mem.recall("明天天气") or "（没有相关记忆，这是对的）")

    os.remove(tmp)
    try:
        input("\n自检完成。按回车退出。")
    except EOFError:
        pass