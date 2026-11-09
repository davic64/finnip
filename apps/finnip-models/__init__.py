"""Model switching shared by Finnip's voice and Telegram.

"usa Opus" / "usa Sonnet" -> the user's Claude subscription (Hermes' anthropic provider);
"usa el normal" / "que el normal sea DeepSeek" -> an OpenRouter model picked by name.
One JSON state file (MODEL_STATE) holds {"use": "opus"|"sonnet"|"normal", "normal": "<OpenRouter id>"}.
Hermes loads this file as a plugin (Telegram); the voice gateway imports it too (read-only mount) and
sends the routed model on every request. Standard library only.
"""
import json
import os
import re
import unicodedata
import urllib.request

SUBSCRIPTION = {"opus": "claude-opus-5-5", "sonnet": "claude-sonnet-5-5"}
STATE_PATH = os.environ.get("MODEL_STATE", "/opt/finnip-models/model.json")
LEADS = {"oye", "hey", "ey", "ok", "okay", "finnip"}
_USE = re.compile(r"^(?:usa|utiliza|cambia|cambiate|pasate|regresa|vuelve)(?: a)?(?: al| el)? (?:modelo )?(opus|sonnet|normal)$")
# A model can't tell which model it is (it repeats what its prompt says), so this is answered from the state.
_WHICH = re.compile(r"^(?:(?:con )?(?:que|cual) (?:modelo|ia|inteligencia artificial) (?:eres|usas|estas usando|tienes|"
                    r"es el que usas|funcionas|respondes|estas)|que modelo de ia eres)$")
_SET_NORMAL = (
    re.compile(r"^(?:que )?el (?:modelo )?normal (?:ahora )?(?:sea|es) (.+)$"),
    re.compile(r"^(?:cambia|pon) (?:el )?(?:modelo )?normal (?:a|en|como) (.+)$"),
    re.compile(r"^usa (.+) como (?:el )?(?:modelo )?normal$"),
)
# Words that mark a special build of a model; skipped unless the user names them ("glm flash").
VARIANTS = {"legal", "batch", "air", "mini", "nano", "lite", "flash", "flashx", "vision", "omni",
            "thinking", "distill", "preview", "free", "exacto", "audio", "image", "search", "online"}


def _norm(text):
    text = unicodedata.normalize("NFKD", text.casefold())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^\w ]", " ", text).split())


def model_order(text):
    """("use", "opus"|"sonnet"|"normal") or ("set_normal", "<name>") for a model order, else None."""
    words = _norm(text).split()
    while words and words[0] in LEADS:
        words = words[1:]  # "Oye Finnip, usa Opus"
    phrase = " ".join(words)
    if match := _USE.match(phrase):
        return "use", match.group(1)
    if _WHICH.match(phrase):
        return "which", None
    for pattern in _SET_NORMAL:
        if match := pattern.match(phrase):
            return "set_normal", match.group(1)
    return None


def pick_model(query, models):
    """Newest OpenRouter id with every word of the query and no variant the user didn't ask for,
    undated builds first ("-1017" is a snapshot). ponytail: name heuristic, no quality ranking;
    the user hears the exact pick and can name a more specific one ("glm 5.3 prime")."""
    want = [w for w in re.split(r"[^a-z0-9.]+", query.lower()) if w]

    def fits(model):
        if ":" in model["id"]:
            return False
        parts = [p for p in re.split(r"[^a-z0-9.]+", model["id"].lower()) if p]
        return all(w in "".join(parts) for w in want) and all(p in want for p in parts if p in VARIANTS)

    dated = lambda m: bool(re.search(r"-\d{4}$", m["id"]))  # noqa: E731
    hits = [m for m in models if fits(m)]
    return max(hits, key=lambda m: (not dated(m), m.get("created", 0)))["id"] if hits else None


def model_label(model_id):
    """'z-ai/glm-5.3-prime' -> 'GLM 5.3 prime' for speech."""
    name = model_id.split("/", 1)[-1].lstrip("~").replace("-", " ")
    return re.sub(r"\b(glm|gpt|qwen\d*|kimi|deepseek)\b",
                  lambda m: m.group(1).upper() if m.group(1) in ("glm", "gpt") else m.group(1).capitalize(), name)


def load_state(path=None):
    path = path or STATE_PATH
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"use": "sonnet", "normal": ""}  # what Finnip used before this existed


def save_state(state, path=None):
    tmp = (path or STATE_PATH) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f)
    os.chmod(tmp, 0o660)  # Hermes and the voice gateway share it through group 10000
    os.replace(tmp, path or STATE_PATH)


def route(state):
    """(provider, model) for Hermes."""
    if state.get("use") == "normal" and state.get("normal"):
        return "openrouter", state["normal"]
    return "anthropic", SUBSCRIPTION.get(state.get("use"), SUBSCRIPTION["sonnet"])


def openrouter_models():
    with urllib.request.urlopen("https://openrouter.ai/api/v1/models", timeout=15) as resp:
        return json.loads(resp.read())["data"]


def apply_order(order, path=None, models=None):
    """Carry out a model order -> (what to tell the user, (provider, model) or None if nothing changed)."""
    kind, value = order
    models = models or openrouter_models
    state = load_state(path)
    if kind == "which":
        provider, model = route(state)
        if provider == "anthropic":
            return f"Ahora uso {state.get('use', 'sonnet').capitalize()} de su suscripción de Claude, señor.", None
        return f"Ahora uso {model_label(model)} por OpenRouter, señor.", None
    if kind == "use" and value in SUBSCRIPTION:
        state["use"] = value
        save_state(state, path)
        return f"Listo, señor. Uso {value.capitalize()} de su suscripción.", route(state)
    if kind == "use":
        if not state.get("normal"):
            return "Aún no tengo un modelo normal, señor. Dígame cuál, por ejemplo: el normal sea DeepSeek.", None
        state["use"] = "normal"
        save_state(state, path)
        return f"Listo, señor. Uso el modelo normal, {model_label(state['normal'])}.", route(state)
    try:
        picked = pick_model(value, models())
    except Exception:
        return "No pude consultar los modelos de OpenRouter, señor.", None
    if not picked:
        return f"No encontré «{value}» en OpenRouter, señor.", None
    state.update(use="normal", normal=picked)
    save_state(state, path)
    return f"Listo, señor. El normal ahora es {model_label(picked)}, y ya lo estoy usando.", route(state)


def telegram_hook(event=None, **kwargs):
    """pre_gateway_dispatch: turn a model order into Hermes' own /model command.
    It runs BEFORE Hermes checks the sender, so it checks TELEGRAM_ALLOWED_USERS itself: nobody else
    may switch the model (the state also drives the voice)."""
    text = getattr(event, "text", None)
    source = getattr(event, "source", None)
    platform = getattr(getattr(source, "platform", None), "value", None)
    if platform != "telegram" or not isinstance(text, str) or text.lstrip().startswith("/") or "\n" in text.strip():
        return None
    order = model_order(text)
    if order is None:
        return None
    allowed = {u.strip() for u in os.environ.get("TELEGRAM_ALLOWED_USERS", "").split(",") if u.strip()}
    if str(getattr(source, "user_id", "")) not in allowed:
        return None
    message, chosen = apply_order(order)
    if chosen is None:
        return {"action": "rewrite", "text": f"[Aviso del sistema: responde al usuario exactamente esto: {message}]"}
    provider, model = chosen
    return {"action": "rewrite", "text": f"/model {model} --provider {provider} --global"}


def register(ctx):
    ctx.register_hook("pre_gateway_dispatch", telegram_hook)
