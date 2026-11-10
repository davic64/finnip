# Spec Delta

## Purpose

Mostrar la pieza diseñada como holograma en el escritorio, para revisarla antes de imprimirla, y manipularla con mouse, voz o gestos de la mano.

## ADDED Requirements

### Requirement: Mostrar la pieza
El overlay de escritorio SHALL mostrar la versión pedida de una pieza en lugar del núcleo, con el estilo del holograma y sus medidas en milímetros, y SHALL volver al núcleo al cerrarla.

#### Scenario: Abrir una pieza
- **WHEN** el usuario dice "enséñame el soporte"
- **THEN** el overlay muestra el soporte con sus medidas y oculta el núcleo

#### Scenario: Cerrar la pieza
- **WHEN** el usuario dice "cierra la pieza"
- **THEN** la pieza desaparece y vuelve el núcleo

### Requirement: Girar y acercar con mouse y voz
Con una pieza abierta, el overlay SHALL girarla al arrastrar y acercarla con la rueda dentro de su recuadro, y SHALL resolver las órdenes de vista por voz sin llamar al modelo. Fuera del recuadro, los clics SHALL seguir llegando a las demás aplicaciones.

#### Scenario: Vista de arriba
- **WHEN** el usuario dice "vista de arriba"
- **THEN** la pieza gira para verse desde arriba

#### Scenario: Clic fuera de la pieza
- **WHEN** el usuario hace clic en otra aplicación fuera del recuadro
- **THEN** el clic llega a esa aplicación

### Requirement: Gestos de la mano
Con una pieza abierta, el overlay SHALL reconocer en la Mac: pellizco y arrastre para girar, pellizco con dos manos para acercar o alejar, mano abierta durante 1 segundo para la vista inicial, y puño para cerrar la pieza. El video de la cámara no SHALL salir de la Mac.

#### Scenario: Girar con la mano
- **WHEN** el usuario junta pulgar e índice y mueve la mano a la derecha
- **THEN** la pieza gira hacia la derecha

#### Scenario: Cerrar con el puño
- **WHEN** el usuario cierra la mano en puño
- **THEN** la pieza se cierra

### Requirement: Cámara solo con una pieza abierta
La cámara SHALL encenderse al abrir una pieza y apagarse al cerrarla.

#### Scenario: Sin pieza
- **WHEN** no hay ninguna pieza abierta
- **THEN** la cámara está apagada
