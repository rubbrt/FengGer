"""读取 prompt.txt，向千问请求一段新的口播语录。"""

import os
from pathlib import Path

from openai import OpenAI

from qianwen_local_tts import backup_generated_text, synthesize_answer


# 这是给模型看的参考答案。它用于说明篇幅、节奏和论证方式。
EXAMPLE_ANSWER = """
“风哥，我女友一直追星怎么办？追那种小鲜肉，然后对比来说我的不是,我该怎么办。”这有什么怎么办的？你女朋友追小鲜肉，然后说你哪儿都不是，那你本来是不是哪儿都不是呢？咱首先把这个问题搞明白。你别一听女朋友说你不如明星，你就觉得自己受到了莫大的侮辱。那你确实不如明星啊。人家长得比你帅，比你高，比你有钱，唱歌有人听，拍个照片几百万人点赞。你呢？你发个朋友圈，半天两个赞，一个是你妈，一个是卖保险的。那你有什么可不服的？难道人家小鲜肉还得输给你？人家一年挣几千万，你一个月挣五千八，还得等公司十五号发工资。你俩要是放在一起比较，人家唯一不如你的地方，可能就是不认识你女朋友。你还在这儿气得睡不着。你气什么呢？你女朋友说太阳比你亮，你是不是还要上天跟太阳打一架？她说珠穆朗玛峰比你高，你是不是买张机票去西藏，站山脚下骂它两句？本来就不是一个层次的东西，有什么好比的？但是你女朋友为什么要拿明星跟你比呢？因为她也追不到明星啊。她要是真能追到，她还跟你在这儿谈什么？人家小鲜肉大半夜给她发一句：“在吗？”她能穿着拖鞋从六楼直接跳下去，落地之后打车去机场。问题是人家根本不知道她是谁。她每天在手机屏幕前：“哥哥好帅。”“哥哥要照顾好自己。”“哥哥最近瘦了，我好心疼。”哥哥晚上吃什么，有营养师管；哥哥瘦没瘦，有经纪人管；哥哥心情好不好，有整个团队管。轮得到她心疼吗？她心疼半天，人家明星银行卡里又多了二十万。她自己第二天还得坐地铁上班。所以她追星本质上跟你打游戏差不多。你打游戏的时候觉得自己是赵云，一枪进场七进七出。游戏一关，你还是坐在出租屋里，外卖盒子三天没扔。她看小鲜肉的时候，觉得自己将来也能找一个这样的。手机一关，看见旁边躺着一个你。心理有落差，很正常。她不是突然发现你不帅。她第一天认识你的时候就知道你长什么样。她跟你谈了这么久，现在才说你不如小鲜肉，这不叫发现事实，这叫拿一个你永远比不过的人恶心你。就跟你天天看女明星，然后对她说：“你看看人家这个腿。”“你看看人家这个脸。”“你看看人家身材管理。”她能高兴吗？她肯定说你不尊重她。那为什么她拿男明星羞辱你，就成了少女追星自由呢？因为你太软了呗。她说一句你不如明星，你就在网上问：“风哥，我应该怎么办？”你还能怎么办？回家参加练习生选秀呗。每天早上六点起来练舞，下午练声乐，晚上研究表情管理。练个三五年，被娱乐公司淘汰之后回来继续给她当男朋友。是不是？你还真想证明自己比明星强啊？你证明不了。而且也没必要证明。问题根本不在明星身上，问题在于你女朋友瞧不上你，但是暂时又没找到比你更合适的。这才是你应该害怕的东西。她如果真觉得你很好，她追十个明星也没用。她会说：“明星是明星，我男朋友是我男朋友。”她现在天天拿明星跟你比，说明她心里已经在给你打分了。今天嫌你不帅，明天嫌你没钱，后天嫌你不会提供情绪价值。她不是想让你变好。她是通过不断说你不行，提前给自己以后离开你找理由。等哪天真有一个条件稍微比你好点的男的出现，她就会跟你说：“其实我们很早以前就不合适了。”你还在那儿回忆：“是不是因为我没有明星帅？”不是。是因为她本来就没多看得起你。所以你也别跟她讲什么大道理。什么“追星可以，但不要比较”。没用。她要是尊重你，不用你教。她要是不尊重你，你写八百字小作文，她看完只会觉得你破防了。你就直接问她：“既然我哪儿都不如他，你为什么不去找他？”她要是说：“我就是开玩笑，你怎么这么小气？”那说明她知道这话伤人，只不过以前觉得你不敢翻脸。她要是继续说：“你本来就比不上啊。”那也很简单。你说：“对，我比不上，那你去找比得上的。”然后结束。你有什么舍不得的？一个天天提醒你自己是次等品的女朋友，你还当宝贝一样供着。你是找对象，还是花钱雇了一个人生差评师？她每天负责点评你的脸、身高、收入和气质，你每天负责接受整改。月底还不用给她发工资。天下还有这种好工作？所以这个事没什么复杂的。她追星不是问题。她瞧不上你才是问题。你条件差也不是最大的问题。条件差还非得赖在一个瞧不上你的人身边，天天等待人家批准你继续当男朋友，这才是最大的问题。人家小鲜肉至少在舞台上唱跳两小时才能挣钱。你女朋友骂你两句，你还给她买礼物。从商业模式上来说，她比小鲜肉成功多了。峰哥说得对不对？”
"""


def build_message(question: str) -> str:
    """Build the shared Qwen prompt used by both CLI and web interfaces."""
    prompt_file = Path(__file__).with_name("prompt.txt")
    prompt_text = prompt_file.read_text(encoding="utf-8")
    return f"""{prompt_text}

---
下面是一条参考答案。请只借鉴表达方法，不要声称自己是“风哥”，
也不要把这条参考答案说成任何真实人物的原话。

参考答案：
{EXAMPLE_ANSWER}

---
现在请为这个新问题生成语录，只输出语录正文：
“风哥，{question}”
"""


def generate_answer(client: OpenAI, message: str, attempt: int) -> str:
    """向千问请求一个候选版本。重新生成时提醒模型更换切入角度。"""
    retry_hint = ""
    if attempt > 1:
        retry_hint = (
            f"\n\n这是第 {attempt} 次生成。请重新构思，换一套切入角度、类比和段落表达，"
            "不要机械重复上一版。"
        )

    response = client.chat.completions.create(
        model=os.getenv("QWEN_MODEL", "qwen-plus"),
        messages=[{"role": "user", "content": message + retry_hint}],
        temperature=0.8,
    )
    answer = response.choices[0].message.content
    if not answer or not answer.strip():
        raise RuntimeError("千问没有返回可用的语录。")
    return answer.strip()


def choose_candidate_action() -> str:
    """让用户决定采用当前候选、重新生成或退出。"""
    while True:
        choice = input(
            "\n请选择：[Enter/1] 满意，进入 TTS  "
            "[2/r] 不满意，重新生成  [q] 退出："
        ).strip().lower()
        if choice in {"", "1", "y", "yes"}:
            return "accept"
        if choice in {"2", "r", "retry", "n", "no"}:
            return "retry"
        if choice in {"q", "quit", "exit"}:
            return "quit"
        print("输入无效，请输入 1、2 或 q。")


def main():
    # input() 会暂停程序，等你在终端输入问题后再继续。
    question = input("请输入新的语录问题：").strip()
    if not question:
        print("问题不能为空，请重新运行程序。")
        return

    # prompt.txt、参考答案和新问题放进同一条 user 消息。
    message = build_message(question)

    # API Key 不写在代码里；先在系统环境变量中设置 DASHSCOPE_API_KEY。
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        print("没有找到 DASHSCOPE_API_KEY 环境变量。")
        return

    client = OpenAI(
        api_key=api_key,
        base_url=os.getenv(
            "QWEN_BASE_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        ),
    )

    attempt = 1
    while True:
        print(f"\n正在生成第 {attempt} 个候选版本……")
        try:
            answer = generate_answer(client, message, attempt)
        except Exception as error:
            print("调用千问 API 失败：", error)
            return

        print(f"\n生成结果（候选 {attempt}）：\n")
        print(answer)

        action = choose_candidate_action()
        if action == "retry":
            attempt += 1
            continue
        if action == "quit":
            print("已退出，当前候选未进行语音合成。")
            return
        break

    # 只备份用户确认采用的版本；后面的 TTS 不会改动备份文件。
    backup = backup_generated_text(answer)
    print(f"\n已采用候选 {attempt}。")
    print(f"原始文本备份：{backup.path}")

    # 本地 GPT-SoVITS 只加载一次，并按“四句一切”自动处理整篇千问结果。
    try:
        tts_result = synthesize_answer(answer, backup, source_question=question)
    except Exception as error:
        # 文本已备份；TTS 失败时保留它，方便稍后排查或重新合成。
        print("\n语音合成失败，但文本备份已保留：", error)
        return

    print(f"语音成品：{tts_result.audio_path}")
    print(f"本地 TTS 清单：{tts_result.manifest_path}")


if __name__ == "__main__":
    main()
