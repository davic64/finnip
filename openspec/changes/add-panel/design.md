# Design

## Decisions
- **API en el voice gateway.**
  - `/api/routines` (GET y PUT) valida y escribe el archivo de forma atómica.
  - `/api/devices`, `/api/modes` y `/api/modes/{slug}` pasan a Home Bridge con la llave del gateway, que nunca llega al navegador.
  - Solo se exponen esas rutas de Home Bridge; los slugs se validan.
- **Protección.**
  - La identidad de Tailscale ya protege todo, salvo `/health` y `/internal`.
  - Los PUT exigen `application/json`, así que un formulario de otro sitio no puede escribir.
- **Página sin build:** `public/panel.html` es HTML y JS planos, en el mismo estilo que la app. No necesita más dependencias.
- **Coincidencia de frases.** La frase de la rutina se compara por ventanas de palabras con `difflib`, y basta 0.85 para que coincida:
  - "Despier, ya llegó papá" coincide;
  - "ya llegó papá", sin "despierta", no.
- **Orden de ejecución.** La rutina corre antes que los modos y la música en el fast path de `finnip-lights`. Primero el modo, luego la música; Finnip solo dice la respuesta.
