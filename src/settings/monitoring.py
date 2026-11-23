from sc4py.env import env

# Sem token, /metrics responde 404. O mesmo segredo é configurado no coletor.
PAINEL_METRICS_TOKEN = env("PAINEL_METRICS_TOKEN", "")
