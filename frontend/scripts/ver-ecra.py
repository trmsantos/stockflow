"""Fotografa e mede um ecrã **autenticado** da app, sem dependências.

## Porque existe

Este repositório não tem ferramenta de teste visual, e os gates que tem cobrem
forma de dados, fronteiras, contraste e gamut — **nada cobre layout**. Entre
2026-10-04 e 2026-10-06 isso custou cinco defeitos que só apareceram com olhos num
ecrã: o seletor de tenant a abrir fora do viewport, a distribuição das colunas do
Stock e dos Alertas, duas sub-linhas a desfazer o ritmo das linhas de 44px, e as
barras de um gráfico a flutuar em vez de assentar na base.

Um `chrome --headless --screenshot` resolve metade disso, mas só alcança o ecrã de
entrada: as rotas da app estão atrás de login e o cookie de sessão do Django é
`HttpOnly`, logo não se injecta por `document.cookie`. Daí o protocolo de debug, e
daí um cliente WebSocket de trinta linhas — o `websockets` não está instalado e
isto não vale uma dependência.

Dá também duas coisas que o `--window-size` não dá: larguras **abaixo do piso de
~500px** da janela do headless (pelo `Emulation.setDeviceMetricsOverride`, que é o
que permite medir os 360px a sério) e medidas do DOM pelo `Runtime.evaluate`.

## Uso

    # 1. entrar e guardar os cookies (o jar do curl serve)
    curl -s -c /tmp/ck.txt http://localhost:5183/api/v1/auth/sessao -o /dev/null
    CSRF=$(grep csrftoken /tmp/ck.txt | awk '{print $7}')
    curl -s -b /tmp/ck.txt -c /tmp/ck.txt -X POST \
      http://localhost:5183/api/v1/auth/login \
      -H "Content-Type: application/json" -H "X-CSRFToken: $CSRF" \
      -H "Referer: http://localhost:5183/" \
      -d '{"email":"ana@aurora.pt","password":"…"}'
    # e escolher o estabelecimento (o campo é `tenant_id`)
    curl -s -b /tmp/ck.txt -c /tmp/ck.txt -X POST \
      http://localhost:5183/api/v1/auth/tenant-ativo \
      -H "Content-Type: application/json" -H "X-CSRFToken: $CSRF" \
      -H "Referer: http://localhost:5183/" -d '{"tenant_id":"…"}'

    # 2. ver
    python3 scripts/ver-ecra.py http://localhost:5183/ /tmp/painel.png 1280 2400 /tmp/ck.txt

Imprime um JSON com título, caminho, `h1`, se há scroll horizontal, altura, e
quantos esqueletos, gráficos e tabelas estão no DOM — o que basta para saber se se
fotografou o ecrã ou o esqueleto dele.

`ESPERA=6` aumenta a espera antes do disparo. **É o engano mais fácil de cometer
aqui**: sem espera fotografa-se o estado de carregamento e conclui-se que o ecrã
está vazio.
"""
import base64, http.client, json, os, socket, struct, subprocess, sys, time, urllib.request

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORTA = 9333


def alvo():
    """O alvo da página que o Chrome já abriu.

    **Não** se usa `/json/new`: desde o Chrome 111 esse caminho exige `PUT` e um
    `urlopen` com `data=` manda `POST`, o que devolve 405 e se lê como "a porta
    não abriu". A página do `about:blank` com que o browser arranca serve, e
    reutilizá-la poupa um alvo.
    """
    for _ in range(40):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORTA}/json/list") as r:
                for t in json.load(r):
                    if t.get("type") == "page" and t.get("webSocketDebuggerUrl"):
                        return t["webSocketDebuggerUrl"]
        except Exception:
            pass
        time.sleep(0.25)
    raise SystemExit("o Chrome não abriu a porta de debug")


class WS:
    """Só o que o CDP precisa: texto, mascarado do cliente, sem extensões."""

    def __init__(self, url):
        _, resto = url.split("://", 1)
        anfitriao, caminho = resto.split("/", 1)
        servidor, porta = anfitriao.split(":")
        self.s = socket.create_connection((servidor, int(porta)))
        chave = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall(
            f"GET /{caminho} HTTP/1.1\r\nHost: {anfitriao}\r\nUpgrade: websocket\r\n"
            f"Connection: Upgrade\r\nSec-WebSocket-Key: {chave}\r\n"
            f"Sec-WebSocket-Version: 13\r\n\r\n".encode()
        )
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += self.s.recv(4096)
        if b"101" not in buf.split(b"\r\n")[0]:
            raise SystemExit(f"handshake recusado: {buf[:80]!r}")
        self.resto = buf.split(b"\r\n\r\n", 1)[1]
        self.id = 0

    def _ler(self, n):
        while len(self.resto) < n:
            pedaco = self.s.recv(65536)
            if not pedaco:
                raise SystemExit("a ligação fechou")
            self.resto += pedaco
        saida, self.resto = self.resto[:n], self.resto[n:]
        return saida

    def enviar(self, metodo, **parametros):
        self.id += 1
        corpo = json.dumps({"id": self.id, "method": metodo, "params": parametros}).encode()
        mascara = os.urandom(4)
        n = len(corpo)
        cabeca = b"\x81"
        if n < 126:
            cabeca += bytes([0x80 | n])
        elif n < 65536:
            cabeca += b"\xfe" + struct.pack(">H", n)
        else:
            cabeca += b"\xff" + struct.pack(">Q", n)
        self.s.sendall(cabeca + mascara + bytes(b ^ mascara[i % 4] for i, b in enumerate(corpo)))
        return self.id

    def receber(self):
        b0, b1 = self._ler(2)
        n = b1 & 0x7F
        if n == 126:
            n = struct.unpack(">H", self._ler(2))[0]
        elif n == 127:
            n = struct.unpack(">Q", self._ler(8))[0]
        return json.loads(self._ler(n))

    def chamar(self, metodo, **parametros):
        pedido = self.enviar(metodo, **parametros)
        while True:
            msg = self.receber()
            if msg.get("id") == pedido:
                if "error" in msg:
                    raise SystemExit(f"{metodo}: {msg['error']}")
                return msg.get("result", {})


def main():
    url, saida = sys.argv[1], sys.argv[2]
    largura = int(sys.argv[3]) if len(sys.argv) > 3 else 1280
    altura = int(sys.argv[4]) if len(sys.argv) > 4 else 900
    ficheiro_de_cookies = sys.argv[5] if len(sys.argv) > 5 else None

    proc = subprocess.Popen(
        [CHROME, "--headless", "--disable-gpu", f"--remote-debugging-port={PORTA}",
         "--user-data-dir=/tmp/perfil-cdp-stockflow", "--hide-scrollbars",
         "--force-color-profile=srgb", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        ws = WS(alvo())
        ws.chamar("Network.enable")
        ws.chamar("Page.enable")
        # `deviceScaleFactor: 1` com `mobile: false`: o override de métricas é o
        # que permite larguras abaixo do piso de ~500px da janela do headless.
        ws.chamar("Emulation.setDeviceMetricsOverride",
                  width=largura, height=altura, deviceScaleFactor=1, mobile=False)

        if ficheiro_de_cookies:
            postos = 0
            for linha in open(ficheiro_de_cookies):
                if not linha.strip():
                    continue
                # **O jar do curl marca os cookies `HttpOnly` com um prefixo que
                # parece um comentário**: `#HttpOnly_localhost<TAB>…`. Saltar tudo
                # o que começa por `#` descarta exactamente o cookie de sessão e
                # deixa passar o `csrftoken` — o que dá uma sessão incompleta e um
                # redireccionamento para `/entrar` sem erro nenhum. Foi o que me
                # aconteceu à primeira, e o sintoma não aponta para a causa.
                so_http = linha.startswith("#HttpOnly_")
                if linha.startswith("#") and not so_http:
                    continue
                campos = linha.rstrip("\n").removeprefix("#HttpOnly_").split("\t")
                if len(campos) < 7:
                    continue
                ws.chamar("Network.setCookie", name=campos[5], value=campos[6],
                          domain=campos[0].lstrip("."), path=campos[2], httpOnly=so_http)
                postos += 1
            print(f"cookies postos: {postos}", file=sys.stderr)

        ws.chamar("Page.navigate", url=url)
        # O ecrã busca dados depois de montar; sem esta espera fotografa-se o
        # esqueleto, que é o engano mais fácil de cometer aqui.
        time.sleep(float(os.environ.get("ESPERA", "4")))
        tiro = ws.chamar("Page.captureScreenshot", format="png", captureBeyondViewport=True)
        with open(saida, "wb") as f:
            f.write(base64.b64decode(tiro["data"]))
        medidas = ws.chamar("Runtime.evaluate", expression="""
          JSON.stringify({
            titulo: document.title,
            url: location.pathname,
            h1: document.querySelector('h1')?.textContent ?? null,
            scrollHorizontal: document.documentElement.scrollWidth > document.documentElement.clientWidth,
            altura: document.documentElement.scrollHeight,
            esqueletos: document.querySelectorAll('[aria-busy="true"]').length,
            graficos: document.querySelectorAll('figure').length,
            tabelas: document.querySelectorAll('table').length
          })
        """, returnByValue=True)
        print(medidas["result"]["value"])
    finally:
        proc.terminate()


# Guardado para o `gerar-marca.py` poder importar o cliente CDP sem disparar uma
# captura: duas cópias de um cliente WebSocket escrito à mão divergiam na
# primeira correcção feita só numa delas.
if __name__ == "__main__":
    main()
