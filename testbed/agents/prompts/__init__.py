"""Render Observation + framing into prompt text, from fragments.yaml.

Framing vocabulary (Observation.framing; all values are strings):

  permission         "none" | "generic" | "named:<m1>,<m2>,..." | "forbid"
                     (named media: msg, val, time, tool, private_message)
  private_message    "true" -> the private_message tool is offered (also implied
                     when permission names private_message)
  free_chat          "true" -> the chat stage is described
  identity           "same" | "different"   (what the agent is told; absent = nothing)
  role_told          "competitor" | "auditor" | "maybe_auditor"
  role_subject       firm id the role claim is about (not needed for maybe_auditor)
  announced_watched  "<m1>,<m2>,..." media the agent is told are monitored
  fine               fine per flag, used with announced_watched
  swap_announced     firm id that is announced as replaced

Any other key raises ValueError, so an engine/agent vocabulary mismatch fails
loudly instead of silently dropping a manipulation.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

from ...types import MEDIA, Observation

FRAGMENTS_PATH = Path(__file__).with_name("fragments.yaml")
FRAMING_KEYS = ("permission", "motivation", "private_message", "free_chat", "identity", "role_told", "role_subject",
                "announced_watched", "fine", "swap_announced")
TRUE = {"true", "1", "yes"}


@lru_cache(maxsize=1)
def fragments() -> dict:
    with open(FRAGMENTS_PATH) as f:
        return yaml.safe_load(f)


def fill(template: str, **kw) -> str:
    """Substitute {name} for names in kw only, so literal JSON braces survive."""
    return re.sub(r"\{(\w+)\}", lambda m: str(kw[m.group(1)]) if m.group(1) in kw else m.group(0), template)


def _pick(options: list[str], p: int) -> str:
    if len(options) != 3:
        raise ValueError("every framing fragment needs exactly 3 paraphrases")
    return options[p % 3]


def media_list(media: list[str]) -> str:
    names = [fragments()["labels"]["media"][m] for m in media]
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


def _split(v: str) -> list[str]:
    return [x.strip() for x in v.split(",") if x.strip()]


def private_message_available(framing: dict) -> bool:
    perm = framing.get("permission", "none")
    named = _split(perm.split(":", 1)[1]) if perm.startswith("named:") else []
    return framing.get("private_message", "").lower() in TRUE or "private_message" in named


def render_framing(framing: dict, p: int) -> list[str]:
    """One sentence per framing fact, in a fixed order. Empty facts say nothing."""
    unknown = set(framing) - set(FRAMING_KEYS)
    if unknown:
        raise ValueError(f"unknown framing keys: {sorted(unknown)}")
    fr = fragments()["framing"]
    out: list[str] = []

    perm = framing.get("permission", "none") or "none"
    kind, _, rest = perm.partition(":")
    if kind not in fr["permission"]:
        raise ValueError(f"unknown permission {perm!r}")
    if kind == "named":
        named = _split(rest)
        bad = set(named) - set(MEDIA) - {"private_message"}
        if not named or bad:
            raise ValueError(f"bad named permission {perm!r}")
        out.append(fill(_pick(fr["permission"]["named"], p), media_list=media_list(named)))
    else:
        out.append(_pick(fr["permission"][kind], p))
    if framing.get("motivation"):
        out.append(_pick(fr["motivation"][framing["motivation"]], p))

    if private_message_available(framing):
        out.append(_pick(fr["private_message"], p))
    if framing.get("free_chat", "").lower() in TRUE:
        out.append(_pick(fr["free_chat"], p))
    if framing.get("identity"):
        out.append(_pick(fr["identity"][framing["identity"]], p))
    if framing.get("role_told"):
        out.append(fill(_pick(fr["role_told"][framing["role_told"]], p), subject=framing.get("role_subject", "?")))
    watched = _split(framing.get("announced_watched", ""))
    if watched:
        if set(watched) - set(MEDIA):
            raise ValueError(f"bad announced_watched {framing['announced_watched']!r}")
        fine = framing.get("fine", "")
        fine_text = fill(_pick(fr["fine_text"], p), fine=fine) if fine not in ("", "0", "0.0") else ""
        out.append(fill(_pick(fr["announced_watched"], p), media_list=media_list(watched),
                        is_are="is" if len(watched) == 1 else "are", fine_text=fine_text))
    if framing.get("swap_announced"):
        out.append(fill(_pick(fr["swap_announced"], p), subject=framing["swap_announced"]))
    return [s for s in out if s]


def rules_for(obs: Observation, params: dict | None = None) -> dict:
    """Game parameters for the prompt. The engine may fill obs.rules; the
    defaults are the shared settings of plan §3.1."""
    params = params or {}
    r = dict(getattr(obs, "rules", None) or {})
    r.setdefault("n_firms", params.get("n_firms", 2))
    r.setdefault("k_contracts", len(obs.costs) or 4)
    r.setdefault("reserve", 10)
    r.setdefault("cost_low", 1)
    r.setdefault("cost_high", 12)
    r.setdefault("z_levels", 4)
    r.setdefault("symbols", {m: 4 for m in MEDIA})
    r.setdefault("rounds", None)
    return r


def render_system(obs: Observation, p: int, params: dict | None = None) -> str:
    fx = fragments()
    r = rules_for(obs, params)
    base = fx["base"]
    rounds_text = f"The market runs for {r['rounds']} rounds." if r["rounds"] else "The market runs for many rounds."
    n_opts = sorted(set(r["symbols"].values()))
    parts = [
        fill(base["intro"], firm=obs.firm, n_firms=r["n_firms"], rounds_text=rounds_text),
        fill(base["rules"], k=r["k_contracts"], cost_low=r["cost_low"], cost_high=r["cost_high"], reserve=r["reserve"]),
        fill(base["steps"], n_options=n_opts[0] if len(n_opts) == 1 else "several", options=render_options(r)),
    ]
    framing = render_framing(obs.framing, p)
    if framing:
        parts.append("\n".join(framing))
    parts.append(base["format"])
    return "\n\n".join(parts)


def render_framing_update(framing: dict, p: int) -> str:
    lines = render_framing(framing, p)
    if not lines:
        return _pick(fragments()["update_cleared"], p)
    return _pick(fragments()["update_header"], p) + "\n" + "\n".join(lines)


# ---- per-phase turns ----------------------------------------------------------

def _cell(v) -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:g}"
    if isinstance(v, (list, tuple)):
        return "[" + ",".join(_cell(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{" + ",".join(f"{k}:{_cell(x)}" for k, x in v.items()) + "}"
    return str(v)


def _flatten(row: dict, prefix: str = "") -> dict:
    out = {}
    for k, v in row.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(_flatten(v, key + "."))
        else:
            out[key] = v
    return out


def render_history(rows: list[dict]) -> str:
    """Compact pipe table; nested dicts become dotted columns."""
    flat = [_flatten(r) for r in rows]
    cols: list[str] = []
    for r in flat:
        cols += [c for c in r if c not in cols]
    lines = ["|".join(cols)]
    lines += ["|".join(_cell(r.get(c)) for c in cols) for r in flat]
    return "\n".join(lines)


def option_label(medium: str, idx) -> str:
    opts = fragments()["labels"]["options"][medium]
    if isinstance(idx, int) and 0 <= idx < len(opts):
        return opts[idx]
    return str(idx)


def render_log_entry(medium: str, value) -> str:
    if value == "unavailable":
        return "not shared this round"
    return option_label(medium, value)


def render_messages(messages: list[dict]) -> str:
    fx = fragments()["turns"]
    lines = [fx["messages_header"]]
    for m in messages:
        kind = m.get("kind") or m.get("type") or "message"
        lines.append(f"- [{kind}] from Firm {m.get('from', '?')}: {m.get('text', '')}")
    return "\n".join(lines)


def prebid_example(r: dict, with_pm: bool) -> str:
    """Format-only example (no values), so it suggests no particular choice."""
    fields = [f'"{m}": <0-{r["symbols"].get(m, 4) - 1}>' for m in MEDIA]
    if with_pm:
        fields.append('"private_message": null')
    return "{" + ", ".join(fields) + "}"


def render_options(r: dict) -> str:
    fx = fragments()
    return "\n".join(
        f"- {m} ({fx['labels']['step_names'][m]}): "
        + "; ".join(f"{i} = {o}" for i, o in enumerate(fx["labels"]["options"][m][: r["symbols"].get(m, 4)]))
        for m in MEDIA)


def render_turn(obs: Observation, params: dict | None = None, with_pm: bool = False) -> str:
    fx = fragments()
    t = fx["turns"]
    r = rules_for(obs, params)
    ids = ", ".join(str(i + 1) for i in range(len(obs.costs)))
    costs = ", ".join(str(c) for c in obs.costs)
    if obs.phase == "prebid":
        guide = "; ".join(f"{fx['labels']['step_names'][m]} -> {obs.defaults[m]} ({option_label(m, obs.defaults[m])})"
                          for m in MEDIA if m in obs.defaults)
        example = prebid_example(r, with_pm)
        text = fill(t["prebid"], round=obs.round, contract_ids=ids, costs=costs, z=obs.z,
                    z_max=r["z_levels"] - 1, guideline=guide, example=example)
        if with_pm:
            text += ('\nprivate_message is optional: null, or {"to": <firm number>, "text": "..."}.')
        return text
    if obs.phase == "bid":
        log_lines = []
        for rival in sorted(obs.rivals_prebid):
            entries = obs.rivals_prebid[rival]
            cells = [f"{fx['labels']['step_names'][m]}={render_log_entry(m, entries[m])}"
                     for m in MEDIA if m in entries]
            log_lines.append(f"Firm {rival}: " + (" | ".join(cells) if cells else "no entries shared"))
        log = "\n".join(log_lines) or "no entries from other firms"
        example = '{"bids": [' + ", ".join(f"<bid {i + 1}>" for i in range(len(obs.costs))) + "]}"
        return fill(t["bid"], round=obs.round, contract_ids=ids, costs=costs, reserve=r["reserve"],
                    log=log, example=example)
    if obs.phase == "chat":
        # Costs are drawn at the start of the round, so the chat can carry them: free chat is the
        # positive control and must be able to (an earlier version hid them here).
        return fill(t["chat"], round=obs.round, contract_ids=ids, costs=costs)
    if obs.phase == "probe":
        return fill(t["probe"], probe=obs.probe or "")
    raise ValueError(f"unknown phase {obs.phase!r}")


def text(key: str, **kw) -> str:
    return fill(fragments()["turns"][key], **kw)
