package com.genealogy.dsllint.highlight

import com.intellij.openapi.editor.DefaultLanguageHighlighterColors
import com.intellij.openapi.editor.colors.TextAttributesKey

object DslTextAttributes {
    val DSL_FUNCTION: TextAttributesKey = TextAttributesKey.createTextAttributesKey(
        "DSL_FUNCTION_CALL",
        DefaultLanguageHighlighterColors.FUNCTION_CALL,
    )

    val DSL_GENDER_ENUM: TextAttributesKey = TextAttributesKey.createTextAttributesKey(
        "DSL_GENDER_ENUM",
        DefaultLanguageHighlighterColors.CONSTANT,
    )

    val DSL_MONTH_ENUM: TextAttributesKey = TextAttributesKey.createTextAttributesKey(
        "DSL_MONTH_ENUM",
        DefaultLanguageHighlighterColors.CONSTANT,
    )

    val DSL_STATUS_CONST: TextAttributesKey = TextAttributesKey.createTextAttributesKey(
        "DSL_STATUS_CONST",
        DefaultLanguageHighlighterColors.CONSTANT,
    )
}
