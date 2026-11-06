#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RoboMemory · 演示程序

它只是 robomemory.py 的一个使用示例：
把这个库接成命令行，让你看见"记得住"是什么感觉。

真正给别人用的东西在 robomemory.py。

用法：
    python memory_bot.py            离线模式
    python memory_bot.py --online   用大模型生成回复（需要 DEEPSEEK_API_KEY）
    python memory_bot.py --reset    清空记忆

命令：
    /mem      看它记住了什么
    /forget   删掉全部记忆
    /body     换一个身体（记忆保留）
    /quit     退出
"""

import os
import sys
import json
import argparse
import datetime
import urllib.request
from pathlib import Path

from robomemory import Memory

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
DB = HERE / "memory.db"
PERSONA = HERE / "人格.txt"

BODIES = [
    ("方头方脑的小盒子", "▪▪"),
    ("圆滚滚的球", "●"),
    ("六足小虫", "✳"),
]
BOT_NAME = "小笨"

BANNER = """
┌──────────────────────────────────────────┐
│  RoboMemory · 机器人记忆体                │
│  它记得你。换个身体，也还记得。            │
└──────────────────────────────────────────┘
"""


def load_persona():
    """读 人格.txt，改名字、改身体，不用动代码。文件不存在就用默认值。"""
    global BOT_NAME
    if not PERSONA.exists():
        return
    try:
        text = PERSONA.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = PERSONA.read_text(encoding="gbk", errors="ignore")
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = [x.strip() for x in line.split("=", 1)]
        if not v:
            continue
        if k in ("身体1", "身体2", "身体3"):
            i = int(k[-1]) - 1
            BODIES[i] = (v, BODIES[i][1])
        elif k == "名字":
            BOT_NAME = v


def offline_reply(hits):
    if not hits:
        return "嗯，记住了。"
    h = hits[0]
    if h["kind"] == "preference":
        return f"我记得你说过「{h['content']}」。这次要我注意吗？"
    if h["kind"] == "episode":
        return f"上次是「{h['content']}」对吧？这回我小心点。"
    return f"你之前提过「{h['content']}」。"


def online_reply(turn, hits):
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not key:
        return offline_reply(hits)
    mem_text = "\n".join(f"- ({h['kind']}) {h['content']}" for h in hits) or "（没有相关记忆）"
    system = (
        "你是一个有长期记忆的家庭机器人。说话短、具体、不客套，一次最多两句话。"
        "如果下面的记忆和当前话题有关，自然地提起来，不要生硬复述。\n"
        f"你记得的事：\n{mem_text}"
    )
    payload = json.dumps({
        "model": os.environ.get("LLM_MODEL", "deepseek-chat"),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": turn},
        ],
        "temperature": 0.7,
        "max_tokens": 200,
    }).encode("utf-8")
    req = urllib.request.Request(
        os.environ.get("LLM_BASE_URL", "https://api.deepseek.com").rstrip("/") + "/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return offline_reply(hits) + f"\n  （联网失败，已降级：{type(e).__name__}）"


def show(rows):
    if not rows:
        print("  （还没有记忆）")
        return
    name = {"fact": "事实", "preference": "偏好", "episode": "情景", "skill": "技能"}
    for r in rows:
        print(f"  #{r['id']:<3} [{name.get(r['kind'], r['kind'])}] {r['content']}   ({r['created_at'][:10]})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--online", action="store_true")
    ap.add_argument("--reset", action="store_true")
    args = ap.parse_args()

    if args.reset and DB.exists():
        DB.unlink()
        print("记忆已清空。")

    mem = Memory(DB)
    load_persona()

    print(BANNER)
    body = int(mem.get_meta("body", 0))
    name, face = BODIES[body]
    print(f"\n{face} 我是{BOT_NAME}，现在这具身体是「{name}」。")
    n = mem.count()
    if n:
        print(f"我记得 {n} 件事。其中：")
        for r in mem.all()[-3:]:
            print(f"  · {r['content']}")
    else:
        print("我还不认识你。")
    print("\n（输入 /mem 看记忆，/body 换身体，/quit 退出）\n")

    reply = (lambda t, h: online_reply(t, h)) if args.online else (lambda t, h: offline_reply(h))

    while True:
        try:
            turn = input("你 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not turn:
            continue
        if turn in ("/quit", "/exit", "/q"):
            print("（记忆已保存）")
            break
        if turn == "/mem":
            show(mem.all())
            continue
        if turn == "/forget":
            mem.forget()
            print("  （关于你的一切，我都不记得了）")
            continue
        if turn == "/body":
            body = (int(mem.get_meta("body", 0)) + 1) % len(BODIES)
            mem.set_meta("body", body)
            name, face = BODIES[body]
            print(f"  {face} 换身体了，我现在是{name}。")
            print(f"  记忆还有 {mem.count()} 条，一条没丢。")
            continue

        hits = mem.recall(turn)
        if hits:
            print("它 > " + reply(turn, hits))
        else:
            items = mem.extract(turn)
            if items:
                print(f"它 > 记住了：{items[0][1]}。")
            else:
                print("它 > 嗯，记住了。")
        n = mem.remember(turn)
        if n:
            print(f"     （悄悄记住 {n} 条）")


if __name__ == "__main__":
    main()
