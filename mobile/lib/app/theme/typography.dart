import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import 'tokens.dart';

/// Type scale from `mobile-plan/04-ui-design-system.md` §1.2 (dark-only
/// vintage brand):
///
/// | Family            | Slots                                        |
/// |-------------------|----------------------------------------------|
/// | Playfair Display  | display (hero 34–40, screen title 28/34) and |
/// |                   | headline (section heading 20/26)             |
/// | EB Garamond       | title, body (16/24), supporting (14/20),     |
/// |                   | caption (12/16), label-caps (11/14)          |
/// | Special Elite     | stamp — see [buildStampStyle]                |
///
/// Notes:
/// * `letterSpacing` is applied per-style here (TextTheme itself has no
///   letterSpacing parameter); label-caps carries `2.0` ≈ web `0.18em`.
/// * `TextTheme` cannot uppercase text — consumers of `labelSmall` render the
///   string uppercase (e.g. the `LabelCaps` widget applies `toUpperCase()`).
/// * Colors follow §1.1/§4 contrast pairs: `ink800` primary text, `ink600`
///   supporting, `ink400` muted/caption. Body never below 12 sp.
TextTheme buildAppTextTheme() {
  return TextTheme(
    // Display — Playfair Display: hero titles, screen titles.
    displayLarge: GoogleFonts.playfairDisplay(
      fontSize: 36,
      height: 1.2,
      fontWeight: FontWeight.w700,
      color: AppColors.ink800,
    ),
    displayMedium: GoogleFonts.playfairDisplay(
      fontSize: 32,
      height: 1.2,
      fontWeight: FontWeight.w700,
      color: AppColors.ink800,
    ),
    // Screen title 28/34.
    displaySmall: GoogleFonts.playfairDisplay(
      fontSize: 28,
      height: 1.21,
      fontWeight: FontWeight.w700,
      color: AppColors.ink800,
    ),
    // Headline — Playfair Display: card & section headings (20/26 baseline).
    headlineLarge: GoogleFonts.playfairDisplay(
      fontSize: 24,
      height: 1.25,
      fontWeight: FontWeight.w600,
      color: AppColors.ink800,
    ),
    headlineMedium: GoogleFonts.playfairDisplay(
      fontSize: 22,
      height: 1.25,
      fontWeight: FontWeight.w600,
      color: AppColors.ink800,
    ),
    headlineSmall: GoogleFonts.playfairDisplay(
      fontSize: 20,
      height: 1.3,
      fontWeight: FontWeight.w600,
      color: AppColors.ink800,
    ),
    // Title — EB Garamond: list row titles, emphasis.
    titleLarge: GoogleFonts.ebGaramond(
      fontSize: 20,
      height: 1.3,
      fontWeight: FontWeight.w600,
      color: AppColors.ink800,
    ),
    titleMedium: GoogleFonts.ebGaramond(
      fontSize: 16,
      height: 1.5,
      fontWeight: FontWeight.w600,
      color: AppColors.ink800,
    ),
    titleSmall: GoogleFonts.ebGaramond(
      fontSize: 14,
      height: 1.43,
      fontWeight: FontWeight.w600,
      color: AppColors.ink800,
    ),
    // Body — EB Garamond 16/24 (primary reading size).
    bodyLarge: GoogleFonts.ebGaramond(
      fontSize: 16,
      height: 1.5,
      fontWeight: FontWeight.w400,
      color: AppColors.ink800,
    ),
    bodyMedium: GoogleFonts.ebGaramond(
      fontSize: 16,
      height: 1.5,
      fontWeight: FontWeight.w400,
      color: AppColors.ink800,
    ),
    // Supporting text 14/20.
    bodySmall: GoogleFonts.ebGaramond(
      fontSize: 14,
      height: 1.43,
      fontWeight: FontWeight.w400,
      color: AppColors.ink600,
    ),
    // Button labels: EB Garamond 600 at the body size (buttons use the body
    // face per §1.2; color is owned by each button's foregroundColor).
    labelLarge: GoogleFonts.ebGaramond(
      fontSize: 16,
      height: 1.25,
      fontWeight: FontWeight.w600,
    ),
    // Caption 12/16 — timestamps, helper text (muted ink, onSurfaceVariant).
    labelMedium: GoogleFonts.ebGaramond(
      fontSize: 12,
      height: 1.33,
      fontWeight: FontWeight.w400,
      color: AppColors.ink400,
    ),
    // label-caps 11/14 — eyebrows & meta labels; uppercase in the widget.
    labelSmall: GoogleFonts.ebGaramond(
      fontSize: 11,
      height: 1.27,
      fontWeight: FontWeight.w600,
      letterSpacing: 2,
      color: AppColors.ink400,
    ),
  );
}

/// The "stamp" role from §1.2 (Special Elite postmark badges, status stamps,
/// IDs). Specialized stamp type has no dedicated [TextTheme] slot, so
/// consumers (e.g. `StampBadge`) take this style directly.
///
/// Defaults to 13 sp — inside the spec's 12–16 sp / 1.4 line-height range.
TextStyle buildStampStyle({
  double fontSize = 13,
  Color color = AppColors.ink800,
}) {
  return GoogleFonts.specialElite(
    fontSize: fontSize,
    height: 1.4,
    color: color,
  );
}
