# SubFuse

Aplicação desktop PySide6 em português para adicionar uma ou mais faixas SRT a
vídeos. Permite guardar as legendas como faixas selecionáveis (softsub) ou
queimar uma faixa na imagem (hardsub).

**English:** SubFuse is a Portuguese-language PySide6 desktop app for embedding
SRT subtitles as selectable tracks or burning them into video.

> **Licenças:** o código está sob MIT. O ícone é uma obra separada, com todos os
> direitos reservados, e não está incluído na licença MIT. A política atual não
> inclui FFmpeg nos binários; consulte
> [Distribuição e licenças](docs/DISTRIBUTION.md).

## Requisitos

- Python 3.10 ou superior.
- `ffmpeg` e `ffprobe` instalados e disponíveis no `PATH`. O SubFuse também
  procura executáveis opcionais em `tools/` junto da aplicação empacotada.
  **Não descarrega ferramentas em runtime.**
- Para hardsub, o FFmpeg tem de incluir o filtro `subtitles` (normalmente
  fornecido por uma compilação com libass). A aplicação verifica o suporte e
  apresenta um erro compreensível quando falta.

O AppImage, o ZIP de Windows e os ZIP de macOS incluem a aplicação e as
bibliotecas necessárias do Python/Qt, mas **não incluem FFmpeg nem ffprobe**.

### Instalar FFmpeg

Instale FFmpeg pelo gestor de pacotes da sua plataforma ou por uma origem
confiável e confirme que `ffmpeg` e `ffprobe` estão no `PATH`:

```sh
ffmpeg -version
ffprobe -version
```

Exemplos: `sudo apt install ffmpeg` em Debian/Ubuntu, `brew install ffmpeg` no
macOS ou `choco install ffmpeg` no Windows. No Windows, abra um terminal novo
depois da instalação para atualizar o `PATH`. Para hardsub, confirme também que
`ffmpeg -filters` lista o filtro `subtitles`.

## Instalar e executar a partir do código

Crie um ambiente virtual e instale o projeto (Linux/macOS):

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev,build]"
python -m legenda_app
```

No Windows PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev,build]"
python -m legenda_app
```

Os launchers existentes continuam disponíveis:

```sh
python embutir_legendas.py
python -m legenda_app
subfuse
```

## Modos de operação

- **Softsub:** copia o vídeo e o áudio sem recodificação e acrescenta os SRT
  como faixas. MKV é recomendado; MP4 converte as legendas para `mov_text`.
  Compatibilidade de codecs/faixas depende do contentor e do leitor.
- **Hardsub:** renderiza uma faixa SRT na imagem com o filtro `subtitles` e
  codifica o vídeo com `libx264`; o áudio é copiado. Produz MP4 e exige suporte
  libass no FFmpeg. Este modo é mais lento e recodifica o vídeo.
- O cancelamento remove a saída temporária e não substitui um ficheiro final
  existente se o processamento falhar ou for cancelado.

## Testes e qualidade

```sh
python -m ruff check .
python -m pytest
```

Os testes de integração geram vídeos pequenos localmente com FFmpeg. Quando
`ffmpeg`, `ffprobe` ou o filtro `subtitles` não estão disponíveis, os testes
dependentes são ignorados com uma razão explícita.

## Builds locais

Os builds são nativos: execute cada comando no sistema e arquitetura-alvo.
Os builds não fazem cross-compilation.

### Linux x86_64 — AppImage

Instale `appimagetool` (e FUSE quando necessário) no sistema, instale os extras
de build e execute:

```sh
python -m pip install -e ".[build]"
packaging/build_appimage.sh
```

Gera `dist/SubFuse-<versão>-linux-x86_64.AppImage` e executa um smoke test
`--version`. O launcher antigo `./build_appimage.sh` continua a funcionar.

### Windows x86_64 — ZIP portátil

No PowerShell, num Windows x86_64:

```powershell
python -m pip install -e ".[build]"
python packaging/build_portable.py
```

Gera `dist/SubFuse-<versão>-windows-x86_64.zip`, com a pasta PyInstaller
portátil. Não é necessário instalador.

### macOS — ZIP portátil

Execute nativamente em cada arquitetura (Apple Silicon **e** Intel):

```sh
python -m pip install -e ".[build]"
python packaging/build_portable.py
```

Gera `dist/SubFuse-<versão>-macos-arm64.zip` ou
`dist/SubFuse-<versão>-macos-x86_64.zip`. São builds distintos; não é
declarado nem produzido um binário universal. O ZIP contém a aplicação `.app`.

## GitHub Actions

- `CI` executa lint, testes com FFmpeg e um smoke test da aplicação em Ubuntu
  x86_64, Windows x86_64, macOS Apple Silicon e macOS Intel, em pushes e pull
  requests.
- `Release` só é acionado por tags `vMAJOR.MINOR.PATCH`, exige que a tag
  corresponda à versão no pacote, constrói cada artefacto em runner nativo,
  calcula `SHA256SUMS` e publica uma GitHub Release. O job de publicação tem
  apenas `contents: write`; builds e CI têm `contents: read`.
- O workflow verifica SHA-256 das versões fixadas do appimagetool e runtime
  AppImage antes de os usar.
- A configuração dos workflows não cria releases a partir de branches ou
  pull requests.

## Estrutura

```text
.
├── .github/workflows/       # CI e release
├── assets/                  # ícone original fornecido
├── docs/                    # decisões de distribuição/licença
├── legenda_app/             # pacote Python e asset incluído
├── packaging/               # AppImage, ZIPs e integração desktop
├── tests/                   # unitários e integração FFmpeg
├── embutir_legendas.py      # launcher compatível
└── pyproject.toml           # versão, dependências, ferramentas e entry points
```

## Limitações e publicação

O código do projeto está licenciado sob MIT. O ícone foi criado pelo
proprietário, que reservou os direitos; a licença do código não concede
permissão para o reutilizar. A política de FFmpeg e as obrigações aplicáveis
estão registadas em [docs/DISTRIBUTION.md](docs/DISTRIBUTION.md).

O AppImage distribuído pelo CI é construído num runner Ubuntu 24.04. A
compatibilidade com versões mais antigas de glibc/distribuições Linux não foi
validada neste ambiente e pode variar.
