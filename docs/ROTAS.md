# Metodologia de Calculo dos Horarios de Onibus

## Resumo

Todos os 233 horarios de onibus foram calculados a partir dos dados oficiais da **API Mobilibus**, que alimenta o app **Bus2You** usado pela SOU Transportes de Americana-SP.

## Fonte dos Dados

### Descoberta da API

O site oficial da SOU Transportes (`soutransportes.com.br/americana/linhas-e-horarios/`) usa um iframe que aponta para um app Flutter:

```html
<iframe src="https://bus2.info/2you/#/4l1q9" ...></iframe>
```

Analisando o codigo JavaScript compilado (`main.dart.js`), foi descoberta a API da Mobilibus.

### Endpoints Utilizados

1. **Detalhes do projeto**
   ```
   GET https://mobilibus.com/api/project-details?project_hash=4l1q9
   → projectId: 481, nome: "Americana, SP"
   ```

2. **Lista de rotas**
   ```
   GET https://mobilibus.com/api/routes?origin=web&project_id=481
   → 28 linhas (102 a 225)
   ```

3. **Horarios de cada rota**
   ```
   GET https://mobilibus.com/api/timetable?origin=web&v=2&project_id=481&route_id={routeId}
   → horarios, direcoes, dias de operacao, trips
   ```

4. **Paradas detalhadas (com coordenadas)**
   ```
   GET https://mobilibus.com/api/trip-details?origin=web&v=2&trip_id={tripId}
   → lista de paradas com lat/lng, nome da rua e numero
   ```

## Metodologia de Calculo

### 1. Geocodificacao dos Enderecos

- **Casa (Jd. da Balsa)**: Coordenadas obtidas via paradas proximas
- **Trabalho (Vila Sta. Catarina)**: Coordenadas via Nominatim/OpenStreetMap (~-22.7511, -47.3280)
- **Faculdade (Jd. Luciene)**: Coordenadas via parada da L.225 na Av. Joaquim Boer, 806 (~-22.7355, -47.2990)

### 2. Identificacao de Linhas Relevantes

Para cada linha/trip:
1. Baixei dados de todas as 28 linhas e seus 55 trips (direcoes)
2. Calculei distancia (Haversine) de cada parada aos 3 pontos de interesse
3. Filtrei linhas que passam a menos de 600m de ambos os enderecos (origem e destino)
4. Verifiquei ordem das paradas para garantir sentido correto (ex: trabalho → faculdade, nao o contrario)

### 3. Calculo de Horario nos Pontos

Cada parada na API tem um campo `int` (inteiro) que representa os **segundos acumulados** desde a saida da origem do trip. Usando isso:

```
Horario no ponto = Horario de saida da origem + offset em segundos da parada
```

#### Offsets Calculados

**Linha 220:**
- Direcao 0 (Mario Covas → Praia Recanto):
  - R. Cira de O. Petrin (Casa): +0 min
  - R. Vieira Bueno (Trabalho): +28.2 min
  - R. Alvaro Cechino (Faculdade): +39.2 min

- Direcao 1 (Praia Recanto → Mario Covas):
  - R. Sao Gabriel (Faculdade): +26.8 min
  - R. Rui Barbosa (Trabalho): +39.5 min
  - R. Luiz Bassete (Casa): +76.4 min

**Linha 213:**
- Direcao 0 (Galpao → Jd. Balsa):
  - R. Parana (Faculdade): +5.0 min
  - R. Brasil (Trabalho): +21.4 min
  - R. Luiz Bassete (Casa): +60.3 min

### 4. Verificacao

Os horarios calculados foram verificados contra dados pre-existentes:
- L.220 Casa→Trabalho: 04:10→04:38 (offset 28min) ✓
- L.220 Casa→Faculdade: 16:50→17:29 (offset 39min) ✓
- Todos os horarios existentes bateram com os calculados

## Rotas e Linhas

### Casa → Trabalho (47 horarios)
- **L.220** (R. Cira de O. Petrin → R. Vieira Bueno): ~28 min
- **L.213** (R. Rio das Velhas → R. Pe. Epifanio Estevan): ~39 min

### Trabalho → Faculdade (64 horarios)
- **L.225** (Av. de Cillo → R. Eugenio Bertine): ~26 min, desembarca a 89m da FAM
- **L.114** (Av. de Cillo → R. Alvaro Cechino): ~13 min
- **L.102** (Av. de Cillo → R. Alvaro Cechino): ~13 min
- **L.103** (R. Ari Meireles → R. Alvaro Cechino): ~15 min, passa a 24m do trabalho
- **L.105** (Av. de Cillo → R. Alvaro Cechino): ~13 min
- **L.118** (Av. de Cillo → R. Alvaro Cechino): ~12 min
- **L.200** (Av. de Cillo → R. Alvaro Cechino): ~14 min
- **L.205** (Av. de Cillo → R. Alvaro Cechino): ~14 min

### Faculdade → Casa (47 horarios)
- **L.220** (R. Sao Gabriel → R. Luiz Bassete): ~50 min
- **L.213** (R. Parana → R. Luiz Bassete): ~55 min

### Casa → Faculdade (28 horarios)
- **L.220** (R. Cira de O. Petrin → R. Alvaro Cechino): ~39 min

### Trabalho → Casa (47 horarios)
- **L.220** (R. Rui Barbosa → R. Luiz Bassete): ~37 min
- **L.213** (R. Brasil → R. Luiz Bassete): ~39 min

## Notas Importantes

- Horarios sao **aproximados** (calculados a partir de offsets da API)
- Dados obtidos em **fevereiro/2026** via API Mobilibus
- Apenas horarios de **dia util** (seg-sex)
- Distancias sao em linha reta (caminhada real pode ser um pouco maior)
- A parada mais usada perto do trabalho (Av. de Cillo, 269) fica a ~516m (~6-7 min andando)
- A L.225 desembarca a ~89m da faculdade, as outras linhas a ~585m (~7 min andando)
