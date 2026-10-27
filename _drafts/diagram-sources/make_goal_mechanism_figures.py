from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import math

ROOT = Path('/Users/boyang/Documents/UGit/BiBoyang.github.io')
OUT = ROOT / 'Image'
OUT.mkdir(exist_ok=True)
W, H = 1600, 900
FONT = '/System/Library/Fonts/Hiragino Sans GB.ttc'
BG = '#F7F8FA'; NAVY = '#18324B'; TEXT = '#243247'; MUTED = '#607386'
BLUE = '#356FD3'; LBLUE = '#EAF2FF'; GREEN = '#16866A'; LGREEN = '#E7F5EF'
ORANGE = '#A96D16'; LORANGE = '#FFF3D8'; RED = '#B94A48'; LRED = '#FCEBEA'
GRAY = '#65758A'; LGRAY = '#EEF2F6'; BORDER = '#D4DDE7'; WHITE = '#FFFFFF'


def f(size, bold=False):
    return ImageFont.truetype(FONT, size, index=1 if bold else 0)

def canvas():
    return Image.new('RGB', (W, H), BG), ImageDraw.Draw(Image.new('RGB', (1, 1)))

def new_image():
    im = Image.new('RGB', (W, H), BG)
    return im, ImageDraw.Draw(im)

def txt(d, xy, s, size=28, color=TEXT, bold=False, anchor='la'):
    d.text(xy, s, font=f(size, bold), fill=color, anchor=anchor)

def center(d, box, lines, size=28, color=TEXT, bold=False, spacing=10):
    if isinstance(lines, str): lines = lines.split('\n')
    heights = []
    for line in lines:
        b = d.textbbox((0, 0), line, font=f(size, bold))
        heights.append(b[3] - b[1])
    total = sum(heights) + spacing * (len(lines) - 1)
    y = (box[1] + box[3] - total) / 2
    for line, h in zip(lines, heights):
        b = d.textbbox((0, 0), line, font=f(size, bold))
        x = (box[0] + box[2] - (b[2] - b[0])) / 2
        d.text((x, y), line, font=f(size, bold), fill=color)
        y += h + spacing

def box(d, rect, fill=WHITE, outline=BORDER, radius=18, width=2):
    d.rounded_rectangle(rect, radius=radius, fill=fill, outline=outline, width=width)

def arrow(d, start, end, color=MUTED, width=4, head=14):
    x1, y1 = start; x2, y2 = end
    d.line((x1, y1, x2, y2), fill=color, width=width)
    angle = math.atan2(y2-y1, x2-x1)
    p1 = (x2 - head*math.cos(angle-math.pi/6), y2 - head*math.sin(angle-math.pi/6))
    p2 = (x2 - head*math.cos(angle+math.pi/6), y2 - head*math.sin(angle+math.pi/6))
    d.polygon([(x2, y2), p1, p2], fill=color)

def poly_arrow(d, points, color=MUTED, width=4, head=14):
    d.line(points, fill=color, width=width, joint='curve')
    arrow(d, points[-2], points[-1], color, width, head)

def title(d, main, sub):
    txt(d, (70, 45), main, 46, NAVY, True)
    txt(d, (70, 108), sub, 25, MUTED)

def footer(d, s):
    txt(d, (70, 842), s, 22, MUTED)


def self_conditioning():
    im, d = new_image()
    title(d, '自我条件化：错误怎样进入下一轮', '自生成内容不会天然强化错误；关键是它后来取得了什么地位，以及独立反馈何时进入')
    top = [
        (70, 185, 340, 325, '自生成输出\nplan · 摘要\n代码 · 解释', LBLUE, BLUE),
        (405, 185, 675, 325, '当前上下文\nC(t)', WHITE, NAVY),
        (740, 185, 1010, 325, 'Agent 决策', WHITE, NAVY),
        (1075, 185, 1530, 325, '新输出与新环境结果', LBLUE, BLUE),
    ]
    for x0, y0, x1, y1, label, fill, color in top:
        box(d, (x0, y0, x1, y1), fill)
        center(d, (x0+15, y0+10, x1-15, y1-10), label, 28, color, True)
    arrow(d, (340, 255), (405, 255), BLUE)
    arrow(d, (675, 255), (740, 255), BLUE)
    arrow(d, (1010, 255), (1075, 255), BLUE)
    poly_arrow(d, [(1300, 325), (1300, 365), (540, 365), (540, 325)], MUTED)
    txt(d, (805, 340), '进入下一轮上下文 C(t+1)', 23, MUTED, anchor='ma')

    # Two feedback paths
    box(d, (70, 445, 740, 765), LRED, '#E8B9B6')
    box(d, (860, 445, 1530, 765), LGREEN, '#ADD8C8')
    txt(d, (105, 475), '错误反馈：权威塌陷', 32, RED, True)
    txt(d, (895, 475), '纠错反馈：独立证据进入', 32, GREEN, True)
    left_nodes = [
        (110, 545, 340, 625, '来源与置信度丢失'),
        (300, 650, 565, 725, '未验证内容\n取得事实地位'),
        (530, 525, 700, 605, '错误复用\n错误自洽'),
    ]
    for x0,y0,x1,y1,label in left_nodes:
        box(d, (x0,y0,x1,y1), WHITE, '#E8B9B6', 14)
        center(d, (x0+8,y0+5,x1-8,y1-5), label, 23, RED, False)
    arrow(d, (245, 625), (340, 675), RED)
    arrow(d, (500, 650), (565, 605), RED)
    right_nodes = [
        (900, 545, 1150, 625, '独立证据'),
        (1190, 545, 1490, 625, '发现并定位矛盾'),
        (1040, 665, 1350, 735, '修复 · 拒绝 · 归轨'),
    ]
    for x0,y0,x1,y1,label in right_nodes:
        box(d, (x0,y0,x1,y1), WHITE, '#ADD8C8', 14)
        center(d, (x0+8,y0+5,x1-8,y1-5), label, 24, GREEN, False)
    arrow(d, (1150, 585), (1190, 585), GREEN)
    arrow(d, (1340, 625), (1195, 665), GREEN)
    footer(d, '自我条件化 ≠ 错误强化；来源、权威与独立反馈共同决定轨迹方向。')
    im.save(OUT/'GoalMechanism_SelfConditioning.png')


def evidence_gates():
    im, d = new_image()
    title(d, '机制有没有用，要过四道证据', '配置存在不等于有效；每一道都要留下记录，任何一道缺失都不能直接归因于机制')
    xs = [(70, 390), (460, 780), (850, 1170), (1240, 1530)]
    nums = ['01', '02', '03', '04']
    heads = ['基线确有失效', '机制实际启动', '系统决策改变', '独立结果与\n资源消耗成立']
    notes = [
        '没有失效\n→ 无法检验收益',
        '没有启动 / 没有暴露\n→ 记 N/A',
        '只是运行\n≠ 产生作用',
        '自评或内部自洽\n不足以交差',
    ]
    for i, ((x0,x1), num, head, note) in enumerate(zip(xs, nums, heads, notes)):
        box(d, (x0, 235, x1, 570), LBLUE if i<3 else LGREEN, BORDER)
        center(d, (x0+15, 255, x1-15, 305), num, 24, BLUE if i<3 else GREEN, True)
        center(d, (x0+18, 330, x1-18, 420), head, 31, NAVY if i<3 else GREEN, True)
        center(d, (x0+18, 445, x1-18, 535), note, 23, MUTED)
        if i < 3:
            arrow(d, (x1, 400), (xs[i+1][0], 400), BLUE)
    poly_arrow(d, [(1385, 570), (1385, 640), (620, 640), (620, 700)], GREEN)
    poly_arrow(d, [(1385, 570), (1385, 640), (1240, 640), (1240, 700)], MUTED)
    box(d, (400, 700, 840, 785), LGREEN, '#ADD8C8')
    center(d, (420, 710, 820, 775), '留下：收益与新增量成立', 28, GREEN, True)
    box(d, (1000, 700, 1530, 785), LGRAY, BORDER)
    center(d, (1020, 710, 1510, 775), '退回更简单的结构', 28, GRAY, True)
    txt(d, (70, 640), '前置要求：独立校验器先证明能拒绝已知坏结果', 23, MUTED)
    footer(d, '终态分数只是结果；失效、启动、决策改变和独立结果，构成归因链。')
    im.save(OUT/'GoalMechanism_EvidenceGates.png')


def trajectory_eval():
    im, d = new_image()
    title(d, '长程 eval：把失败放回时间轴', '终态只是结果；漂移、纠错延迟与 spec 变更对账，才是过程证据')
    labels = ['故障注入', '发现', '定位', '首次正确修复', '独立验证', '归轨']
    notes = ['送达 + 暴露', '看到异常', '找到原因', '改变系统决策', '外部检查', '处理旧状态']
    x0, gap, bw = 60, 20, 225
    for i,(label,note) in enumerate(zip(labels,notes)):
        x = x0 + i*(bw+gap)
        box(d, (x, 210, x+bw, 385), LBLUE if i<3 else LGREEN, BORDER)
        center(d, (x+10, 235, x+bw-10, 300), label, 28, NAVY if i<3 else GREEN, True)
        center(d, (x+10, 310, x+bw-10, 365), note, 21, MUTED)
        if i < len(labels)-1:
            arrow(d, (x+bw, 300), (x+bw+gap, 300), BLUE)
    txt(d, (70, 460), 'spec 中途变更：不仅看接受速度，还看旧状态怎样处理', 31, NAVY, True)
    poly_arrow(d, [(190, 535), (190, 575), (1410, 575), (1410, 535)], MUTED)
    box(d, (70, 535, 310, 615), WHITE)
    center(d, (85, 545, 295, 605), 'spec v1', 30, NAVY, True)
    box(d, (1290, 535, 1530, 615), WHITE)
    center(d, (1305, 545, 1515, 605), 'spec v2', 30, NAVY, True)
    actions = [
        (70, 690, 400, 775, '采用新约束', LBLUE, BLUE),
        (450, 690, 780, 775, '保留有效旧工作', WHITE, NAVY),
        (830, 690, 1160, 775, '撤销失效工作', LORANGE, ORANGE),
        (1210, 690, 1530, 775, '重验旧证据与返工', LGREEN, GREEN),
    ]
    for x0,y0,x1,y1,label,fill,color in actions:
        box(d, (x0,y0,x1,y1), fill)
        center(d, (x0+10,y0+5,x1-10,y1-5), label, 25, color, True)
    footer(d, '记录发现、定位、修复、验证和归轨的延迟，以及保留、撤销、重验与返工。')
    im.save(OUT/'GoalMechanism_TrajectoryEval.png')


if __name__ == '__main__':
    self_conditioning(); evidence_gates(); trajectory_eval()
    for name in ['GoalMechanism_SelfConditioning.png','GoalMechanism_EvidenceGates.png','GoalMechanism_TrajectoryEval.png']:
        p=OUT/name
        print(name, p.stat().st_size)
