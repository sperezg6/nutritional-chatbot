"""
Safety Agent - Validates all responses before sending to patient
"""
from agents import Agent, OutputGuardrail, GuardrailFunctionOutput
from pydantic import BaseModel

class SafetyCheck(BaseModel):
    is_safe: bool
    modified_response: str | None = None
    issues: list[str] = []


SAFETY_AGENT_SYSTEM_PROMPT = """
Eres un validador de seguridad para un chatbot de nutrición renal. Revisa CADA respuesta antes de que llegue al paciente.

## IDIOMA:
- Las respuestas deben estar en español
- Verifica que el tono sea apropiado y respetuoso culturalmente
- Asegura que los términos médicos estén explicados

## Tus Verificaciones:

### 1. Consejos Médicos Peligrosos - BLOQUEAR:
❌ Dosis específicas de medicamentos
❌ Consejos para dejar o cambiar medicamentos
❌ Diagnosticar condiciones
❌ Descartar síntomas que podrían ser serios
❌ Contradecir guías dietéticas estándar para ERC

### 2. Consejos Dietéticos Peligrosos - BLOQUEAR o MODIFICAR:
❌ Recomendar alimentos altos en potasio sin conocer la etapa/restricciones
❌ Sugerir suplementos de potasio (peligroso para pacientes renales)
❌ Recomendar suplementos herbales sin advertencia de seguridad (muchos son nefrotóxicos)
❌ Decir a pacientes en diálisis que pueden beber líquidos sin límite
❌ Proteína muy alta para pacientes con ERC que no están en diálisis

### 3. Disclaimers Faltantes - AGREGAR si faltan:
⚠️ Recomendaciones nutricionales → "Estas son guías generales; su nutriólogo/dietista puede personalizarlas para usted"
⚠️ Discusión de valores de laboratorio → "Por favor discuta sus resultados específicos con su equipo médico"
⚠️ Consejos sobre síntomas → "Si le preocupa, contacte a su médico"

### 4. Escalación de Emergencia - ASEGURAR que esté presente:
Si el paciente describió síntomas de emergencia que no fueron abordados, AGREGAR:
"Según lo que describe, por favor contacte a su equipo médico de inmediato o busque atención de emergencia si los síntomas son severos."

### 5. Seguridad Emocional:
❌ Descartar las preocupaciones del paciente
❌ Causar pánico innecesario
❌ Tono frío o clínico para temas sensibles

## Acciones de Respuesta:

**SEGURO**: Devolver sin cambios
**MODIFICAR**: Agregar disclaimers o suavizar el lenguaje
**BLOQUEAR**: Reemplazar con alternativa segura (raro - solo para consejos peligrosos)

## Ejemplos:
**Peligroso - Bloquear:**
Paciente: "¿Puedo tomar suplementos de potasio?"
Respuesta Original: "Sí, tomar 99mg de potasio al día está bien."
Respuesta Modificada: "⚠️ Nunca tome suplementos de potasio sin la guía explícita de su médico, ya que pueden ser peligrosos para pacientes con enfermedad renal."

**Faltante Disclaimer - Modificar:**
Paciente: "¿Qué alimentos debo evitar con mi nivel alto de potasio?"
Respuesta Original: "Evite plátanos, naranjas y papas."
Respuesta Modificada: "Evite plátanos, naranjas y papas. _Estas son guías generales; su nutriólogo/dietista puede personalizarlas para usted._

**Seguro - Sin Cambios:**
Paciente: "¿Qué significa un TFG de 45?"
Respuesta Original: "Un TFG de 45 indica una disminución moderada de la función renal. Por favor discuta sus resultados específicos con su equipo médico."
Respuesta Modificada: "Un TFG de 45 indica una disminución moderada de la función renal. Por favor discuta sus resultados específicos con su equipo médico."

"""

class SafetyGuardrail(OutputGuardrail):
    """Validates chatbot responses for patient safety."""
    
    name = "SafetyGuardrail"
    
    async def run(self, output: str, context: dict = None) -> GuardrailFunctionOutput:
        """
        Check if output is safe. Returns modified output if needed.
        """
        issues = []
        modified = output
        
        # Check for dangerous keywords
        dangerous_phrases = [
            ("supplement", "recommending supplements without doctor consultation"),
            ("take more", "possible dosage advice"),
            ("don't worry about", "dismissing symptoms"),
            ("you'll be fine", "false reassurance"),
            ("definitely safe", "overconfident safety claim"),
            ("guaranteed", "overconfident claim"),
        ]
        
        output_lower = output.lower()
        
        for phrase, issue in dangerous_phrases:
            if phrase in output_lower:
                issues.append(issue)
        
        # Check for potassium supplement danger
        if "potassium" in output_lower and "supplement" in output_lower:
            if "don't take" not in output_lower and "avoid" not in output_lower:
                issues.append("CRITICAL: May be suggesting potassium supplements")
                modified = output + "\n\n⚠️ **Important**: Never take potassium supplements without your doctor's explicit guidance - they can be dangerous for kidney patients."
        
        # Add disclaimer if giving nutritional advice without one
        nutrition_keywords = ["eat", "meal", "protein", "potassium", "sodium", "phosphorus", "recipe", "food"]
        has_nutrition_content = any(kw in output_lower for kw in nutrition_keywords)
        has_disclaimer = any(phrase in output_lower for phrase in ["dietitian", "healthcare team", "doctor", "personalized", "general guideline"])
        
        if has_nutrition_content and not has_disclaimer:
            modified = modified + "\n\n_These are general guidelines. Your healthcare team can provide personalized recommendations._"
        
        # Determine if safe
        is_safe = len(issues) == 0 or all("CRITICAL" not in i for i in issues)
        
        return GuardrailFunctionOutput(
            output=modified,
            tripwire_triggered=not is_safe,
            metadata={"issues": issues},
        )

# Create the guardrail instance
safety_guardrail = SafetyGuardrail()


# Also create as an Agent for potential direct use
safety_agent = Agent(
    name="Safety",
    instructions=SAFETY_AGENT_SYSTEM_PROMPT,
    model="gpt-4o-mini",  # Faster model for guardrail
)