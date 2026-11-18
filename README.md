# 带材检测站录像交班

白班操作员收到离线灰度相机已经封定的触发包。质检员用拍摄时的固定规格复核暗窗。晚班接班员在相机停用后按窗口号领取原帧和设备位置，安排人工复查。

## 白班采集与晚班领取

1. 登记相机、配置修订、像素宽高和灰度门槛。
2. 打开绑定指定修订的班次。后来登记的修订可供其他班次使用。
3. 从离线回放逐条领取已封定的密集触发包。
4. 检查班次相机、声明区间、原始槽序、每帧形状、载荷和出处。
5. 累计有效像素数及灰度总和，按固定门槛分级。
6. 同一事务封存配置副本、窗口身份、原帧、出处和统计。提交后领取窗口号。
7. 关闭回放源与归档连接。晚班用同一个数据库重开，按班次和窗口号领取。
8. 复核时核对固定摘要，根据分级选择候选，再从原帧复算并汇总交班清单。

## 计量、来源与失效边界

槽号和设备位置为从零起的非负整数，含义分别是包内声明的绝对样本槽和设备记录的原始位置。声明闭区间包含触发槽，并由收到的帧以原顺序逐槽覆盖。每像素占一字节。宽和高分别匹配已绑定规格，空包、缺槽、重复槽、错序和错相机都会拒收。

灰度值为 0 至 255。0 是有效像素。对原帧字节使用整数累计，保存 `(gray_sum, pixel_count)`。当 `gray_sum < threshold * pixel_count` 时标为 `dark`，否则标为 `pass`。三张单像素 10、20、30 的总和是 60，计数为 3，门槛 20 时通过。另一组 0、20 的均值为 10，在同一门槛下标暗。

原包身份为班次和包号。原样重投复用窗口编号、统计和分级，包含帧形状、原始字节及每帧设备出处在内的任一内容改动均构成冲突。归档写入失败回滚本次新窗。已发布窗口的固定摘要覆盖身份、区间、配置、统计、分级和帧摘要，帧摘要独立覆盖帧顺序、样本槽、原字节和出处。按号领取时检查两层摘要及密集布局。交班在同一读快照内先检查本班次固定摘要，再检查和复算选中窗口。任一核验失败时整次交班报错。报告按整数触发槽、窗口号排序，同触发槽的独立窗口均保留。

## Python API

需要 Python 3.11 标准库。`Station` 实例拥有一条 SQLite 连接，独立读者可另开实例。关闭或重开数据库保留已登记修订、班次和窗口。

```python
from station import Station
from source.replay import ReplaySource

with Station('shift.sqlite3') as station:
    key = station.profiles.register_profile('C1', 'R1', 1, 1, 20)
    binding = station.sessions.open_session('A', key)
    with ReplaySource(open('samples/day-shift.jsonl', encoding='utf-8')) as source:
        while (packet := source.next_packet()) is not None:
            receipt = station.capture.capture_packet(binding.session, packet)
            print(receipt.capture_id, receipt.totals, receipt.grade.value)

with Station('shift.sqlite3') as station:
    fixed = station.windows.read_window('A', 1)
    report = station.review.handover('A', dark_only=True)
    print(fixed, report)
```

- `register_profile(camera, revision, width, height, threshold)` 返回 `ProfileKey`。同键同内容重复登记幂等，异文抛出 `ProfileConflictError`。非法规格抛出 `ValueError`。
- `open_session(session, profile_revision)` 返回 `SessionBinding`。改绑或未知修订抛出 `SessionBindingError`。
- `ReplaySource.next_packet()` 正常到尾返回 `None`。坏行或坏包抛出 `TapeRecordError` 或 `PacketFormatError`，后续调用可领取下一记录。关闭后调用抛出 `ReplayClosedError`，重复关闭安全。
- `capture_packet(session, packet)` 返回 `CaptureReceipt`。不合格包抛出 `AdmissionError`，同号异文抛出 `PacketConflictError`，SQLite 写入错误传给调用者。
- `read_window(session, capture_id)` 返回 `ArchivedWindow` 或 `None`。证据损坏抛出 `ArchiveVerificationError`。
- `handover(session, dark_only)` 返回 `HandoverEntry` 列表。合法空班次返回空列表，未知班次抛出 `SessionBindingError`，证据损坏抛出 `ArchiveVerificationError`。

回放文件为 UTF-8 JSON Lines，每行一包。包字段为 `camera`、`packet_id`、`trigger_slot`、`first_slot`、`last_slot` 和 `frames`。每帧含 `slot`、`width`、`height`、`gray_hex` 和 `origin`。`gray_hex` 每两位表示一个原字节，`origin` 含 `camera`、`device`、`position`。调用方也可直接构造 `PacketHeader`、`SourcePacket`、`GrayFrame` 和 `FrameOrigin`。

## 运行

```sh
python3 -B station.py verify
python3 -B station.py demo
```

verify 发现并执行全部确定性回归，失败返回非零。demo 使用新的临时 SQLite 数据库读取 `samples/day-shift.jsonl`，停源并重开，输出两项 `POINTWISE_SCENARIO` 记录。记录包含样例的独立手算、实际领取值和实际交班值。
