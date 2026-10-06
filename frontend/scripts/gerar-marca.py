"""Gera os ficheiros da marca a partir dos tokens e das fontes do projecto.

## Porque é um script e não três binários commitados

Um PNG de logótipo é um ficheiro opaco: ninguém que o abra sabe de que ciano é
feito nem em que corte da Archivo foi composto, e quando a paleta mudar ele fica
calado e errado. Isto deriva-os — a cor vem do `tokens.css` e a fonte do pacote
`@fontsource/archivo` que a aplicação já usa —, logo regenerá-los é correr isto, e
uma divergência entre a marca e o produto deixa de poder acontecer em silêncio.

## O que gera

- `docs/marca/stockflow-wordmark.png` e `…-claro.png` — o lockup com fundo
  **transparente**, em duas tintas. **Duas e não uma**, e a razão é de uso: a
  primeira tem o nome em `foreground` (quase branco) e só se lê sobre escuro;
  um README do GitHub é claro ou escuro conforme quem o abre, e um wordmark
  branco sobre papel desaparece sem ninguém avisar. A segunda usa o
  `--color-background` do produto como tinta — o preto frio da identidade —, logo
  as duas continuam a ser feitas dos mesmos tokens.
- `frontend/public/apple-touch-icon.png` — o azulejo de 180px, com fundo, que é o
  que o iOS usa e o que não aceita SVG.

O favicon é o `public/favicon.svg` e **não** se gera aqui: um SVG escrito à mão lê-se,
e o comentário dele explica a marca melhor do que qualquer PNG.

## A composição

A Archivo **900** — o corte mais pesado da família que a aplicação já possui. É o
"fonte diferente" do pedido resolvido dentro da família em vez de com um tipo
alheio: um tipo de outra família ao lado do produto lê-se como colado por cima, e
a 900 ao lado da 500 do corpo é inconfundivelmente outra coisa sem deixar de ser a
mesma voz. Não entra no browser — vive só aqui e no PNG.

Uso: `python3 scripts/gerar-marca.py`
"""
import base64, http.server, importlib.util, os, shutil, socketserver, subprocess
import tempfile, threading, time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
FRONTEND = AQUI.parent
RAIZ = FRONTEND.parent
PORTA = 8799

# O cliente CDP vive no `ver-ecra.py`: um cliente WebSocket escrito à mão em dois
# ficheiros divergiria na primeira correcção feita só num deles.
_spec = importlib.util.spec_from_file_location("ver_ecra", AQUI / "ver-ecra.py")
assert _spec and _spec.loader
ver_ecra = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ver_ecra)


def token(nome: str) -> str:
    """O valor de um token de cor, lido do `tokens.css`. Uma fonte, não duas."""
    css = (FRONTEND / "src/styles/tokens.css").read_text()
    for linha in css.splitlines():
        if linha.strip().startswith(f"--color-{nome}:"):
            return linha.split(":", 1)[1].split(";")[0].strip()
    raise SystemExit(f"token --color-{nome} não encontrado no tokens.css")


FUNDO, ACENTO, FRENTE = token("background"), token("primary"), token("foreground")

PAGINA = f"""<!doctype html><html><head><meta charset="utf-8"><style>
  @font-face {{
    font-family: "Archivo"; font-style: normal; font-weight: 900;
    font-display: block; src: url("./archivo-900.woff2") format("woff2");
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ background: transparent; }}

  /* O lockup: o trilho e o nome, com a altura do trilho igual à altura das
     maiúsculas — é o que faz os dois lerem-se como uma peça e não como um
     elemento ao lado de outro. */
  .lockup {{
    display: inline-flex; align-items: center; gap: 28px;
    padding: 56px 64px; font-family: "Archivo";
  }}
  .trilho {{ width: 20px; height: 96px; background: {ACENTO}; border-radius: 4px; }}
  .nome {{
    font-weight: 900; font-size: 128px; line-height: 0.78;
    letter-spacing: -0.015em; color: {FRENTE}; text-transform: uppercase;
  }}

  /* O azulejo: a mesma marca do favicon, em grande, com fundo próprio — um
     ícone de aplicação é desenhado sobre o que o sistema quiser. */
  /* A variante para fundo claro: a tinta é o preto frio da identidade, não um
     cinzento qualquer. O trilho mantém-se — o acento foi escolhido para se ler
     nas duas direcções e é o que torna a marca reconhecível em qualquer fundo. */
  .nome.tinta-escura {{ color: {FUNDO}; }}

  .azulejo {{
    width: 180px; height: 180px; background: {FUNDO}; border-radius: 40px;
    display: grid; grid-template-columns: auto 1fr; align-items: center;
    gap: 20px; padding: 40px 36px;
  }}
  .azulejo .trilho {{ width: 20px; height: 100px; border-radius: 7px; }}
  .barras {{ display: flex; flex-direction: column; gap: 32px; }}
  .barra {{ height: 18px; border-radius: 7px; }}
  .barra.forte {{ width: 100%; background: {FRENTE}; }}
  .barra.fraca {{ width: 62%; background: {token("border")}; }}
</style></head><body>
  <div id="wordmark" class="lockup"><span class="trilho"></span><span class="nome">StockFlow</span></div>
  <div id="wordmark-claro" class="lockup"><span class="trilho"></span><span class="nome tinta-escura">StockFlow</span></div>
  <div id="azulejo" class="azulejo">
    <span class="trilho"></span>
    <span class="barras"><span class="barra forte"></span><span class="barra fraca"></span></span>
  </div>
</body></html>"""


def servir(pasta: Path):
    class Mudo(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(pasta), **k)

        def log_message(self, *a):
            pass

    # `allow_reuse_address`: sem isto a porta fica em TIME_WAIT e a segunda
    # corrida seguida falha com "Address already in use" — que é o que me
    # aconteceu, e o erro aponta para a porta e não para a causa.
    socketserver.TCPServer.allow_reuse_address = True
    servidor = socketserver.TCPServer(("127.0.0.1", PORTA), Mudo)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    return servidor


def main() -> None:
    fonte = FRONTEND / "node_modules/@fontsource/archivo/files/archivo-latin-900-normal.woff2"
    if not fonte.exists():
        raise SystemExit(f"falta a fonte: {fonte}. Corre `pnpm install` primeiro.")

    with tempfile.TemporaryDirectory() as tmp:
        pasta = Path(tmp)
        (pasta / "index.html").write_text(PAGINA)
        shutil.copy(fonte, pasta / "archivo-900.woff2")
        servidor = servir(pasta)

        proc = subprocess.Popen(
            [ver_ecra.CHROME, "--headless", "--disable-gpu",
             f"--remote-debugging-port={ver_ecra.PORTA}",
             "--user-data-dir=/tmp/perfil-marca-stockflow", "--hide-scrollbars",
             "--force-color-profile=srgb", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            ws = ver_ecra.WS(ver_ecra.alvo())
            ws.chamar("Page.enable")
            ws.chamar("Emulation.setDeviceMetricsOverride",
                      width=1600, height=600, deviceScaleFactor=2, mobile=False)
            # Fundo transparente de verdade: sem isto o PNG vem com o branco do
            # browser por baixo e deixa de servir sobre uma página escura.
            ws.chamar("Emulation.setDefaultBackgroundColorOverride",
                      color={"r": 0, "g": 0, "b": 0, "a": 0})
            ws.chamar("Page.navigate", url=f"http://127.0.0.1:{PORTA}/")
            time.sleep(2.5)

            for seletor, destino in [
                ("#wordmark", RAIZ / "docs/marca/stockflow-wordmark.png"),
                ("#wordmark-claro", RAIZ / "docs/marca/stockflow-wordmark-claro.png"),
                ("#azulejo", FRONTEND / "public/apple-touch-icon.png"),
            ]:
                caixa = ws.chamar("Runtime.evaluate", returnByValue=True, expression=f"""
                  (() => {{ const r = document.querySelector("{seletor}").getBoundingClientRect();
                     return JSON.stringify({{x: r.x, y: r.y, width: r.width, height: r.height, scale: 1}}); }})()
                """)["result"]["value"]
                import json as _json
                tiro = ws.chamar("Page.captureScreenshot", format="png",
                                 clip=_json.loads(caixa), captureBeyondViewport=True)
                destino.parent.mkdir(parents=True, exist_ok=True)
                destino.write_bytes(base64.b64decode(tiro["data"]))
                print(f"  {destino.relative_to(RAIZ)}  ({destino.stat().st_size // 1024} KB)")
        finally:
            proc.terminate()
            servidor.shutdown()
            # `shutdown()` pára o ciclo e **não** fecha o socket. Faltava, e é a
            # outra metade do "Address already in use".
            servidor.server_close()


if __name__ == "__main__":
    main()
