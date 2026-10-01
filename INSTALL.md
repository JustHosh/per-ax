# Instalar

Todavía no publicamos releases propios, así que hay dos caminos: correrlo desde el código
(ver el [README](README.md)) o generar tu propio instalador `SmitelessSetup.exe` y usarlo como
cualquier programa.

## Generar el instalador

Solo en la PC donde compilas (quien lo instale no necesita nada de esto):

1. Python 3.11+ con las dependencias: `pip install pyinstaller -r requirements.txt`.
2. [AutoHotkey v2](https://www.autohotkey.com/) y su compilador **Ahk2Exe**
   (`C:\Program Files\AutoHotkey\Compiler\Ahk2Exe.exe`).
3. En PowerShell, desde la raíz del repo:

   ```
   powershell -ExecutionPolicy Bypass -File dist\build.ps1
   ```

   El resultado queda en `build\SmitelessSetup.exe`.

## Instalarlo

1. Abre `SmitelessSetup.exe`. Si Windows muestra "Windows protegió tu PC", es porque el
   programa no está firmado: **Más información → Ejecutar de todas formas**.
2. Deja marcada **Start with Windows** si quieres que se abra solo en champ select y en
   partida (sin eso hay que abrirlo a mano antes de jugar). Se puede cambiar después en
   Ajustes → STARTUP.
3. **Install**. Se instala en `%LOCALAPPDATA%\Smiteless` y crea accesos directos en el
   escritorio y en el menú Inicio.
4. Pon League en modo **Sin bordes** (Configuración → Video → Modo de ventana), o el overlay no
   se verá encima del juego.

## Usarlo

- Busca la **S** dorada junto al reloj (si no está, en la flechita `^`).
- **Ctrl+Alt+X** abre el tablero (o tu perfil fuera de partida); **Ctrl+Alt+B** abre el widget.
- Clic derecho en la S: tablero, perfil, widget, ajustes, notas de versión.

## Clave de Riot (para rank, historial y scout)

1. Entra a [developer.riotgames.com](https://developer.riotgames.com) con tu cuenta de Riot.
2. Copia la **Development API Key** (`RGAPI-...`; usa *Regenerate* si está vacía).
3. En la app: **Ajustes → RIOT API KEY → Paste → Save key** (o la barra RIOT KEY del tablero).

La clave de desarrollo caduca cada 24 horas; la app te avisa cuando hay que pegar una nueva.

## Región

Viene en **LAN**. Si juegas en otro servidor: **Ajustes → REGION**.

## Desinstalar

Menú Inicio → Smiteless → Uninstall Smiteless (o Configuración de Windows → Aplicaciones). Tus
ajustes e historial quedan en `%APPDATA%\Smiteless`; bórrala si no los quieres conservar.
