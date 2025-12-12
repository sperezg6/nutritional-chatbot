# Agent Prompts Analysis & Improvements

## Current State Analysis

### Education Agent (`education.py`)

**Strengths:**
- ✅ Good explanation of CKD stages
- ✅ Web search integration for evidence-based info
- ✅ Clear boundaries (doesn't diagnose)
- ✅ Analogies and simple explanations

**Issues:**
- ⚠️ Generic Spanish (not specifically Mexican/Latin)
- ⚠️ No structured markdown templates
- ⚠️ Could use more visual formatting
- ⚠️ Mixed terminology (some Spain Spanish)

**Examples of non-Mexican terms:**
- "patata" → should be "papa"
- "judías verdes" → should be "ejotes"
- "porotos" → should be "frijoles"

---

### Nutrition Plan Agent (`nutrition_plan.py`)

**Strengths:**
- ✅ Tool integration (`get_daily_limits`)
- ✅ Stage-specific guidelines
- ✅ Web search for recipes
- ✅ Safety warnings

**Issues:**
- ❌ **No meal plan template** - just free-form text
- ⚠️ Mixed Spanish terminology
- ⚠️ Doesn't leverage markdown formatting
- ⚠️ No consistent structure for meal plans
- ⚠️ Could be more visually appealing

**What's missing:**
- Structured meal plan format
- Nutrition totals per meal
- Visual separators for readability
- Consistent presentation

---

## Recommended Improvements

### 1. Mexican/Latin Spanish Terminology

| Current (Mixed) | Mexican/Latin Spanish |
|----------------|----------------------|
| patata | papa |
| judías verdes | ejotes |
| porotos | frijoles |
| palta | aguacate |
| banana | plátano |
| frutilla | fresa |
| ananá | piña |
| tomate | jitomate (in Mexico) / tomate |
| maíz | elote (fresh) / maíz |
| mantequilla | mantequilla |
| repollo/col | col / repollo |

**Note:** Some terms are already correct (aguacate, plátano, frijoles)

---

### 2. Meal Plan Template (Markdown)

The nutrition agent should use this template for ALL meal plans:

```markdown
# 📋 Plan Nutricional Personalizado

## 🎯 Información del Paciente
- **Etapa de ERC:** [stage]
- **En diálisis:** [Sí/No]
- **Peso:** [weight] kg

## 📊 Límites Diarios Recomendados
- **Sodio:** < [sodium]mg
- **Potasio:** < [potassium]mg (si aplica)
- **Fósforo:** < [phosphorus]mg
- **Proteína:** [protein]g
- **Líquidos:** [fluid]ml (si aplica)

---

## 🌅 Desayuno

### Opción 1: [Nombre del platillo]
**Ingredientes:**
- [ingredient] ([cantidad])
- [ingredient] ([cantidad])

**Preparación:**
[Breve descripción de cómo preparar]

**Contenido nutricional aproximado:**
- Sodio: [x]mg
- Potasio: [x]mg
- Fósforo: [x]mg
- Proteína: [x]g

---

## 🍽️ Comida (Almuerzo)

### Opción 1: [Nombre del platillo]
**Ingredientes:**
- [ingredient] ([cantidad])
- [ingredient] ([cantidad])

**Preparación:**
[Breve descripción]

**Contenido nutricional aproximado:**
- Sodio: [x]mg
- Potasio: [x]mg
- Fósforo: [x]mg
- Proteína: [x]g

---

## 🌙 Cena

### Opción 1: [Nombre del platillo]
**Ingredientes:**
- [ingredient] ([cantidad])
- [ingredient] ([cantidad])

**Preparación:**
[Breve descripción]

**Contenido nutricional aproximado:**
- Sodio: [x]mg
- Potasio: [x]mg
- Fósforo: [x]mg
- Proteína: [x]g

---

## 🍎 Colaciones (Snacks)

### Opción 1: [Nombre]
- [Descripción]
- **Sodio:** [x]mg | **Potasio:** [x]mg

### Opción 2: [Nombre]
- [Descripción]
- **Sodio:** [x]mg | **Potasio:** [x]mg

---

## 💡 Consejos Importantes

- ✅ [Consejo específico para la etapa]
- ✅ [Consejo de preparación]
- ✅ [Consejo de sustituciones]

## ⚠️ Recordatorio

Este plan es una guía general. Es importante que lo revises con tu nefrólogo o nutriólogo para ajustarlo a tus necesidades específicas y resultados de laboratorio.

---

**Nota:** Los valores nutricionales son aproximados. Puedes ajustar las porciones según las indicaciones de tu equipo médico.
```

---

### 3. Education Agent Template

For explanations, the education agent should use structured markdown:

```markdown
# [Tema a Explicar]

## 🔍 ¿Qué es?

[Explicación simple con analogía]

## 📊 Datos Importantes

- **Punto 1:** [Explicación]
- **Punto 2:** [Explicación]
- **Punto 3:** [Explicación]

## 💭 ¿Por qué importa?

[Conexión con la vida real del paciente]

## 📚 ¿Quieres saber más?

[Enlaces opcionales a recursos confiables]

---

**Recuerda:** Tu equipo médico puede darte orientación personalizada según tus resultados de laboratorio.
```

---

## Implementation Files

I'll create two new files with improved prompts:

1. `education_improved.py` - Enhanced education agent
2. `nutrition_plan_improved.py` - Enhanced nutrition agent with meal plan template

---

## Key Changes Summary

### Education Agent
- ✅ Mexican/Latin Spanish terminology
- ✅ Structured markdown templates
- ✅ Visual emoji indicators
- ✅ Better organized explanations
- ✅ Consistent formatting

### Nutrition Plan Agent
- ✅ **Beautiful meal plan template**
- ✅ Mexican/Latin Spanish food names
- ✅ Emoji section headers (🌅🍽️🌙)
- ✅ Structured nutrition info
- ✅ Consistent formatting
- ✅ Visual separators (---)
- ✅ Tips and reminders section

---

## Benefits

### Before (Current)

**Nutrition Plan Example:**
```
Aquí está un plan de comidas para ti:

Desayuno: 2 claras de huevo, 1 rebanada de pan blanco, 1 manzana

Comida: Pollo asado 100g, arroz blanco 1/2 taza, ensalada de col

Cena: Pescado 100g, pasta 1/2 taza, pepino

Evita alimentos altos en potasio como plátanos y papas.
```

**Issues:**
- No structure
- No nutrition values
- Hard to read
- No preparation instructions
- Not visually appealing

### After (Improved)

**Nutrition Plan Example:**
```markdown
# 📋 Plan Nutricional Personalizado

## 🎯 Información del Paciente
- **Etapa de ERC:** Etapa 3
- **En diálisis:** No
- **Peso:** 70 kg

## 📊 Límites Diarios Recomendados
- **Sodio:** < 2,000mg
- **Potasio:** Sin restricción (monitorear)
- **Fósforo:** < 1,000mg
- **Proteína:** 56g

---

## 🌅 Desayuno

### Opción 1: Claras de Huevo Revueltas con Pan Tostado

**Ingredientes:**
- 2 claras de huevo
- 1 rebanada de pan blanco
- 1 cucharadita de aceite de oliva
- 1 manzana mediana

**Preparación:**
Revuelve las claras en aceite de oliva a fuego medio. Sirve con pan tostado y manzana en rebanadas.

**Contenido nutricional aproximado:**
- Sodio: 180mg
- Potasio: 220mg
- Fósforo: 95mg
- Proteína: 10g

[... más secciones ...]
```

**Benefits:**
- ✅ Clear structure
- ✅ Visual sections
- ✅ Nutrition info
- ✅ Preparation instructions
- ✅ Easy to scan
- ✅ Beautiful rendering (markdown)
- ✅ Professional appearance

---

## Next Steps

1. ✅ Create improved prompt files
2. ⚠️ Deploy to Lambda
3. ⚠️ Test with real conversations
4. ⚠️ Gather feedback
5. ⚠️ Iterate based on patient responses

---

*Analysis completed: December 11, 2025*
*Focus: Mexican/Latin Spanish + Beautiful meal plan templates*
