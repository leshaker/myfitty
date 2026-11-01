from myfitty.metrics.constants import HR_ONLY_SPORTS
from myfitty.metrics.trimp import trimp
from myfitty.metrics.tss import hr_tss, power_tss


def score_activity(summary: dict, thresholds: dict, sport: str | None = None) -> dict:
    """Score one activity from its stored summary and the thresholds in effect on its date.

    summary: moving_seconds, normalized_power, hr_histogram ({bpm: seconds} or None).
    thresholds: ftp, threshold_hr, max_hr (each possibly None).
    Power TSS wins over hrTSS, except for HR-only sports (running), where power is ignored;
    otherwise the activity is unscored with a reason.
    """
    ftp, thr, mx = (thresholds.get(k) for k in ("ftp", "threshold_hr", "max_hr"))
    npw = summary.get("normalized_power")
    if sport in HR_ONLY_SPORTS:
        npw = None
    hist = summary.get("hr_histogram") or None
    out = dict(tss=None, tss_method=None, trimp=None, ftp_used=None, thr_hr_used=None,
               max_hr_used=None, unscored_reason=None)

    tss = None
    if npw and ftp:
        tss, _ = power_tss(npw, ftp, summary.get("moving_seconds"))
        if tss is not None:
            out.update(tss=tss, tss_method="power", ftp_used=ftp)
    if tss is None and hist and thr:
        tss = hr_tss(hist, thr)
        out.update(tss=tss, tss_method="hr", thr_hr_used=thr)
    if tss is None:
        out["unscored_reason"] = "no_threshold" if (npw or hist) else "no_data"

    t = trimp(hist, mx)
    if t is not None:
        out.update(trimp=t, max_hr_used=mx)
    return out
