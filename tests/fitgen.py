"""Minimal FIT file writer for test fixtures.  `python -m tests.fitgen` regenerates tests/fixtures/."""
import math
import struct
from datetime import datetime, timezone
from pathlib import Path

FIT_EPOCH = 631065600  # 1989-12-31T00:00:00Z in unix seconds

# base types: (id, struct format, invalid value)
ENUM, UINT8, SINT32, UINT16, UINT32, UINT32Z = 0x00, 0x02, 0x85, 0x84, 0x86, 0x8C
_FMT = {ENUM: "B", UINT8: "B", SINT32: "<i", UINT16: "<H", UINT32: "<I", UINT32Z: "<I"}

_CRC = [0x0000, 0xCC01, 0xD801, 0x1400, 0xF001, 0x3C00, 0x2800, 0xE401,
        0xA001, 0x6C00, 0x7800, 0xB401, 0x5000, 0x9C01, 0x8801, 0x4400]


def crc16(data: bytes, crc: int = 0) -> int:
    for b in data:
        for nib in (b & 0xF, (b >> 4) & 0xF):
            tmp = _CRC[crc & 0xF]
            crc = (crc >> 4) & 0x0FFF
            crc ^= tmp ^ _CRC[nib]
    return crc


def fit_ts(dt: datetime) -> int:
    return int(dt.timestamp()) - FIT_EPOCH


class Writer:
    def __init__(self):
        self.body = bytearray()
        self._defs: dict[int, tuple] = {}

    def message(self, local: int, global_num: int, fields: list[tuple[int, int, int]]):
        """fields: (field number, base type, value); a tuple value is written as an array field.
        Re-emits the definition if it changed."""
        count = lambda v: len(v) if isinstance(v, tuple) else 1  # noqa: E731
        sig = (global_num, tuple((n, t, count(v)) for n, t, v in fields))
        if self._defs.get(local) != sig:
            self._defs[local] = sig
            self.body += struct.pack("<BBBHB", 0x40 | local, 0, 0, global_num, len(fields))
            for n, t, v in fields:
                size = struct.calcsize(_FMT[t].lstrip("<")) * count(v)
                self.body += struct.pack("BBB", n, size, t)
        self.body += struct.pack("B", local)
        for _, t, v in fields:
            for item in (v if isinstance(v, tuple) else (v,)):
                self.body += struct.pack(_FMT[t] if _FMT[t].startswith("<") else "<" + _FMT[t], item)

    def finish(self) -> bytes:
        header = struct.pack("<BBHI4s", 14, 0x20, 2132, len(self.body), b".FIT")
        header += struct.pack("<H", crc16(header))
        data = header + bytes(self.body)
        return data + struct.pack("<H", crc16(data))


def semicircles(deg: float) -> int:
    return int(round(deg * (2 ** 31) / 180))


SPORTS = {"generic": 0, "running": 1, "cycling": 2}
SUB_SPORTS = {"generic": 0, "indoor_cycling": 6, "road": 7, "street": 2, "virtual_activity": 58}


def make_fit(*, start: datetime, seconds: int, sport: str | None, sub_sport: str | None = None,
             serial: int | None = 1, power=None, hr=None, gps=False, file_type: int = 4,
             session: bool = True, gap: tuple[int, int] | None = None, array_fields: bool = False,
             origin: tuple[float, float] = (47.0, 8.0)) -> bytes:
    """Build an activity FIT file with one record per second.

    power / hr: callables t -> value (or None for absent).  gap: (from_t, to_t) of seconds
    with no records (a pause).  file_type 4 = activity; anything else has no session.
    """
    w = Writer()
    fid = [(0, ENUM, file_type), (1, UINT16, 255), (4, UINT32, fit_ts(start))]
    if serial is not None:
        fid.append((3, UINT32Z, serial))
    w.message(0, 0, fid)
    if file_type != 4:
        return w.finish()

    dist, moving = 0.0, 0
    last_t = 0
    for t in range(seconds):
        if gap and gap[0] <= t < gap[1]:
            continue
        ts = fit_ts(start) + t
        f = [(253, UINT32, ts)]
        if gps:
            f += [(0, SINT32, semicircles(origin[0] + 0.0001 * t)),
                  (1, SINT32, semicircles(origin[1] + 0.0001 * math.sin(t / 60)))]
        dist += 5.0
        f.append((5, UINT32, int(dist * 100)))
        if array_fields:  # high-rate recording: three samples per record, as some Garmin devices write
            f += [(73, UINT32, (4000, 4100, 4200)), (78, UINT32, (5000, 5000, 5010))]
        if hr:
            f.append((3, UINT8, int(hr(t))))
        if power:
            f.append((7, UINT16, int(power(t))))
        w.message(1, 20, f)
        moving += 1
        last_t = t
    if session:
        s = [(253, UINT32, fit_ts(start) + last_t), (2, UINT32, fit_ts(start)),
             (7, UINT32, (last_t + 1) * 1000), (8, UINT32, moving * 1000),
             (9, UINT32, int(dist * 100))]
        if sport is not None:
            s.append((5, ENUM, SPORTS[sport]))
            if sub_sport is not None:
                s.append((6, ENUM, SUB_SPORTS[sub_sport]))
        w.message(2, 18, s)
    return w.finish()


RIDE_START = datetime(2026, 3, 10, 7, 0, 0, tzinfo=timezone.utc)
RUN_START = datetime(2026, 3, 11, 17, 30, 0, tzinfo=timezone.utc)
INDOOR_START = datetime(2026, 3, 12, 6, 0, 0, tzinfo=timezone.utc)


def ride_power_hr(**kw) -> bytes:
    # 20 min: 60 s at 150 W / 60 s at 250 W alternating, with a 30 s pause at t=300..330
    args = dict(start=RIDE_START, seconds=1200, sport="cycling", sub_sport="road", serial=111, gps=True,
                power=lambda t: 150 if (t // 60) % 2 == 0 else 250, hr=lambda t: 120 + (t // 60) % 2 * 30,
                gap=(300, 330))
    args.update(kw)
    return make_fit(**args)


def run_hr_only(**kw) -> bytes:
    args = dict(start=RUN_START, seconds=600, sport="running", sub_sport="street", serial=222,
                gps=True, hr=lambda t: 150)
    args.update(kw)
    return make_fit(**args)


def indoor_nosensor() -> bytes:
    return make_fit(start=INDOOR_START, seconds=300, sport="cycling", sub_sport="indoor_cycling", serial=333)


def array_fields_ride() -> bytes:
    return make_fit(start=datetime(2026, 3, 14, 8, 0, 0, tzinfo=timezone.utc), seconds=120, sport="cycling",
                    sub_sport="road", serial=666, hr=lambda t: 130, array_fields=True)


def virtual_ride() -> bytes:
    """A Zwift-style ride: GPS in a game world in the South Pacific."""
    return make_fit(start=datetime(2026, 3, 15, 18, 0, 0, tzinfo=timezone.utc), seconds=300, sport="cycling",
                    sub_sport="virtual_activity", serial=777, gps=True, power=lambda t: 200, hr=lambda t: 140,
                    origin=(-21.7, 167.0))


def no_sport() -> bytes:
    return make_fit(start=datetime(2026, 3, 13, 8, 0, 0, tzinfo=timezone.utc), seconds=120, sport=None,
                    serial=444, hr=lambda t: 100)


def non_activity() -> bytes:
    return make_fit(start=RIDE_START, seconds=0, sport=None, file_type=2, serial=555)


def corrupt() -> bytes:
    return ride_power_hr()[:400]


FIXTURES = {
    "ride_power_hr.fit": ride_power_hr,
    "run_hr_only.fit": run_hr_only,
    "indoor_nosensor.fit": indoor_nosensor,
    "no_sport.fit": no_sport,
    "virtual_ride.fit": virtual_ride,
    "array_fields.fit": array_fields_ride,
    "non_activity.fit": non_activity,
    "corrupt.fit": corrupt,
}


def write_fixtures(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for name, fn in FIXTURES.items():
        (out / name).write_bytes(fn())


if __name__ == "__main__":
    write_fixtures(Path(__file__).parent / "fixtures")
