# Decisões de distribuição

## FFmpeg e ffprobe

**Decisão atual: não os incluir nos artefactos.** AppImage, ZIP Windows e ZIP
macOS incluem apenas a aplicação e as dependências Python/Qt. Os utilizadores
instalam FFmpeg/ffprobe por uma origem à sua escolha e disponibilizam-nos no
`PATH`.

O código procura primeiro executáveis opcionais em `tools/` no bundle e depois
no `PATH`. Não existe transferência de executáveis durante a execução. Isto
permite preparar bundles futuros sem escolher ou redistribuir uma compilação
antes de validar origem, arquitetura e obrigações legais.

Antes de incluir FFmpeg, o proprietário deve escolher e registar, por sistema e
arquitetura:

- fornecedor e URL da compilação, versão, hash e arquitetura;
- configuração/opções de build e se a compilação é LGPL ou GPL;
- bibliotecas e codecs incluídos, respetivas licenças/avisos e eventuais
  implicações de patentes;
- notices e fontes/código-fonte correspondentes a fornecer com a distribuição.

As obrigações variam com a configuração usada: FFmpeg pode ser distribuído sob
LGPL ou GPL conforme componentes/opções de build, e codecs podem ter licenças
ou restrições adicionais. Não se pode inferir o estado legal só pelo nome
“FFmpeg”. A ausência do FFmpeg nos bundles evita escolher implicitamente uma
compilação e reduz o risco de redistribuição não verificada; não elimina a
necessidade de verificar as restantes dependências empacotadas, incluindo Qt /
PySide6.

## Licença do código do SubFuse

O proprietário escolheu a licença **MIT** para o código do projeto. Consulte o
ficheiro `LICENSE`.

## Ícone

O proprietário confirmou que criou o ícone e detém os direitos. O aviso
`assets/ICON-NOTICE.txt` reserva todos os direitos do ícone e permite hospedá-lo
neste repositório e incluí-lo em builds oficiais do SubFuse. Isso não concede
uma licença geral para extrair, modificar, relicenciar ou reutilizar a imagem
independentemente. O MIT do código não se aplica ao ícone. O asset original e
a cópia incluída no pacote têm o mesmo SHA-256:

```text
4750ff5603ae72d3ff1fca4d8ee129281ab8e88390452da75c12b7507e447bde
```

O aviso documenta a declaração de autoria do proprietário, mas não é prova de
autoria por si só. Mantenha os ficheiros-fonte do desenho e registos datados da
criação. Se o ícone for reutilizado por terceiros sem autorização, preserve os
registos e procure aconselhamento jurídico adequado.

## Artefactos

- Linux: AppImage nativo x86_64.
- Windows: ZIP portátil nativo x86_64, sem instalador.
- macOS: ZIP com `.app` nativa Apple Silicon arm64 e ZIP separado Intel x86_64.
  Não é criado binário universal.

Os alvos macOS são executados nos runners correspondentes do GitHub Actions.
A aceitação final depende de builds e smoke tests bem-sucedidos nesses runners;
uma execução local Linux não valida os alvos Windows/macOS.

O workflow de release fixa e verifica os SHA-256 do appimagetool e runtime
AppImage publicados pelas releases oficiais do projeto AppImage. Atualizar
essas ferramentas exige atualizar e rever também os hashes no workflow.
