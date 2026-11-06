# RoboMemory

给机器人用的长期记忆模块。零依赖，一个 Python 文件，一个 sqlite 数据库。

机器人普遍"做完就忘"：你说一句它做一次，第二天像第一次见你。
这个模块让它记住三件事——**你的偏好、发生过的事、它学会的操作**。

## 接进你自己的机器人（三行）

把 `robomemory.py` 拷到你的项目里：

```python
from robomemory import Memory

mem = Memory("memory.db")          # 记忆库就是一个文件
mem.remember("我怕黑，晚上别关灯")   # 从一句话里抽取并记住
print(mem.recall("今晚有点暗"))      # 想起来相关的事
```

输出：

```python
[{'kind': 'preference', 'content': '我怕黑，晚上别关灯', 'score': 0.275, ...}]
```

## 接到真实机器人里

记忆模块不关心你的机器人长什么样。典型接法：

```python
# 1) 语音识别出用户说话后，先记下来
mem.remember(asr_result)

# 2) 执行任务前，把相关记忆塞进提示词
hits = mem.recall(task_name)
context = "\n".join(h["content"] for h in hits)

# 3) 任务结束后，把结果写成一条情景记忆
mem.add("episode", f"{task_name} 失败，原因是夹爪打滑", 0.8)
```

换机器人、换身体、换机器，把 `memory.db` 拷过去就行。

## API

| 方法 | 作用 | 返回 |
| --- | --- | --- |
| `remember(text)` | 从一段话里抽取并存入 | 写入条数 |
| `add(kind, content, conf)` | 直接写一条（适合传感器事件、任务结果） | 1 |
| `recall(query, k=3)` | 找最相关的 k 条 | `[{kind, content, score, ...}]` |
| `all()` | 全部记忆，按时间排序 | `[{id, kind, content, confidence, created_at}]` |
| `count()` | 一共几条 | int |
| `forget_one(id)` | 删一条 | 删除条数 |
| `forget()` | 全删 | 删除条数 |
| `set_meta(k, v)` / `get_meta(k)` | 存点杂项状态（当前身体、上次巡检时间等） | — |

记忆分四类，`kind` 取值：

| kind | 记什么 | 例子 |
| --- | --- | --- |
| `fact` | 客观事实 | 用户住 6 楼，没有电梯 |
| `preference` | 喜好和雷区 | 我怕黑，晚上别关灯 |
| `episode` | 发生过的事 | 上次搬杯子摔了，夹爪打滑 |
| `skill` | 学会的操作 | 拿杯子要先降 2cm 再闭合 |

## 跑演示

只想看效果，不想读代码：

```bash
python memory_bot.py
```

需要 Python 3.10+，不需要安装任何第三方库。
它会自动生成 `memory.db`。

演示里的命令：

| 命令 | 作用 |
| --- | --- |
| `/mem` | 看记住了什么 |
| `/forget` | 全删 |
| `/body` | 换个"身体"（只是演示，记忆不动） |
| `/quit` | 退出 |

## 文件

| 文件 | 是什么 |
| --- | --- |
| `robomemory.py` | **库本体**。别人只需要这一个文件 |
| `memory_bot.py` | 演示程序，用这个库写的一个命令行聊天 |
| `人格.txt` | 演示用的名字和三个身体 |
| `memory.db` | 运行时生成的记忆文件，不提交 |

## 检索是怎么做的

`recall()` 打分 = 字面重合 × 0.75 + 新旧程度 × 0.25。

- 先比"两个字一组"的碎片（准），没命中再退到单字重合（宽），这样换个说法也能想起来。
- 一个字都对不上的记忆直接不返回——宁可说"没印象"，也不硬凑。

## 设计取舍

- **SQLite 而不是向量库**：几十到几万条记忆，字面匹配够用；零依赖意味着换台电脑也能跑，不会因为装不上向量库当场黑屏。
- **规则抽取而不是模型抽取**：先把链路跑通。要换成大模型，只改 `Memory.extract()` 一个方法，接口不变。
- **留了 `forget` 和 `forget_one`**：用户有权让机器人忘掉自己。没有这个接口，它就是个录音机。

## 已知限制

- 检索基于字面重合，同义词（怕黑 / 不敢关灯）召回较弱。
- 规则抽取会漏掉隐含表达，比如"那屋太黑了"不会识别成怕黑。
- 单进程写入，不支持并发。
- 未在 RDK 板端实测，在 Windows + Python 3.12 验证。

## 开源参考

本项目是独立实现，未直接调用下列库的代码。记忆分层参考了它们的设计：

| 项目 | 地址 | 参考了什么 |
| --- | --- | --- |
| mem0 | https://github.com/mem0ai/mem0 | 抽取 / 检索 / 更新三段式 |
| Letta（原 MemGPT） | https://github.com/letta-ai/letta | 有状态 Agent 的记忆分层 |
| Zep | https://github.com/getzep/zep | 情景记忆 + 时间衰减 |
| MemOS | https://github.com/MemTensor/MemOS | 记忆类型划分 |
| LangMem | https://github.com/langchain-ai/langmem | 语义 / 情景 / 程序性三分 |

## 许可

MIT
