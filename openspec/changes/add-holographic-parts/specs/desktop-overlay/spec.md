# Spec Delta

## ADDED Requirements

### Requirement: Modo pieza en el overlay
El overlay de escritorio SHALL poder mostrar una pieza en lugar del núcleo. Mientras la pieza está abierta, el overlay SHALL recibir el mouse solo dentro del recuadro de la pieza y SHALL tener la cámara encendida para los gestos. Al cerrarla, SHALL volver al núcleo, dejar pasar todos los clics y apagar la cámara.

#### Scenario: Abrir y cerrar
- **WHEN** se abre una pieza y luego se cierra
- **THEN** el overlay vuelve a mostrar el núcleo, deja pasar los clics y la cámara queda apagada
