# Tasks

## 1. Verificación previa del formato de Fish

- [x] 1.1 Pedir a Fish Audio (`s2.1-pro-free`, voz `ae74d1059517440aa6e5d2d50598d179`, `format: "opus"`) una frase corta y confirmar con `ffprobe` dentro del contenedor que el resultado es Ogg/Opus con duración mayor a cero; si no lo es, registrar en design.md el cambio a pedir `mp3` y dejar que Hermes convierta

## 2. Plugin `finnip-voice`

- [x] 2.1 Crear `apps/finnip-voice/plugin.yaml` (versión `0.1.0`) y `apps/finnip-voice/__init__.py` con un `TTSProvider` llamado `fish` registrado en `register(ctx)` mediante `ctx.register_tts_provider`, y verificar que `python -m py_compile` pasa
- [x] 2.2 Implementar `synthesize`: lee `FISH_API_KEY` por llamada, usa los defaults de voz y modelo salvo kwargs, pide `opus` (escrito como `.ogg`) para `ogg`/`opus` o salida `.ogg` y `mp3` en otro caso, sin enviar `language`; `voice_compatible` devuelve `True`. Verificar con los tests de 2.4
- [x] 2.3 Implementar el manejo de errores: falla sin llamar a la red si falta la key, convierte los errores HTTP y de red en mensajes cortos sin la key ni los encabezados, y trata la respuesta vacía como error sin escribir archivo. Verificar con los tests de 2.4
- [x] 2.4 Escribir `apps/finnip-voice/tests/test_plugin.py` (`unittest`, stub de `agent.tts_provider` y `urlopen` simulado) que cubra la URL, los encabezados, el cuerpo, la voz y el modelo por defecto y configurados, la selección opus/mp3, la key faltante, el saneamiento de errores HTTP y de red y la respuesta vacía; verificar que `python -m unittest discover -s apps/finnip-voice/tests -v` pasa
- [x] 2.5 Agregar el job `finnip-voice` a `.github/workflows/ci.yml` (Python 3.13, `py_compile` y `unittest`) y verificar que pasa en el PR
- [x] 2.6 Documentar en `README.md` el plugin, la variable `FISH_API_KEY`, las claves `tts`/`voice`, los comandos `/voice on|tts|off` y el procedimiento de despliegue, y verificar que los comandos documentados coinciden con los del Migration Plan

## 3. Despliegue (requiere aprobación explícita)

- [x] 3.1 Respaldar `data/hermes/config.yaml`, copiar el plugin a `data/hermes/plugins/finnip-voice/` y verificar con `diff` que coincide con `apps/finnip-voice/`
- [x] 3.2 Agregar `finnip-voice` a `plugins.enabled` y fijar `tts.provider: fish`, `tts.output_format: opus` y `voice.auto_tts: true`; validar el YAML con `ruamel.yaml` en el contenedor y reiniciar `hermes`, verificando en `gateway.log` que el gateway arranca sin errores del plugin

## 4. Verificación de integración en Telegram

- [ ] 4.1 Tras `/new`, enviar una nota de voz y verificar que llegan el texto y una nota de voz reproducible con la voz elegida; anotar el tiempo de llegada de la voz desde `agent.log`
- [ ] 4.2 Verificar `/voice tts` (un texto recibe voz), `/voice off` (una nota de voz recibe solo texto) y restaurar el modo deseado
- [ ] 4.3 Con `FISH_API_KEY` vacía de forma temporal o una voz inválida en `tts.voice`, verificar que llega solo el texto y que ni `errors.log` ni `agent.log` muestran la key; después restaurar la configuración

## Workflow follow-up

- Abrir el PR con los artefactos de OpenSpec y la implementación, y hacer merge tras la revisión.
- Archivar el change (`/opsx:archive`) cuando el despliegue y la verificación de integración estén completos.
