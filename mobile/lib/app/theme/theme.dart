import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import 'tokens.dart';
import 'typography.dart';

/// Dark-only Material 3 theme for the vintage batch-studio brand.
///
/// Implements `mobile-plan/04-ui-design-system.md` §1 (color-role mapping,
/// typography, scaffold chrome). MVP ships `darkTheme: appTheme` with
/// `ThemeMode.dark` (§7) — there is no light variant by design.
ThemeData buildAppTheme() {
  final TextTheme textTheme = buildAppTextTheme();

  // Role mapping per §1.1 table; unspecified roles fall back to warm,
  // palette-consistent containers (no Material purple/blue defaults).
  const ColorScheme colorScheme = ColorScheme.dark(
    primary: AppColors.oxblood500,
    onPrimary: AppColors.ink50,
    primaryContainer: AppColors.oxblood600,
    onPrimaryContainer: AppColors.ink50,
    secondary: AppColors.brass400,
    onSecondary: AppColors.ink900,
    secondaryContainer: AppColors.brass600,
    onSecondaryContainer: AppColors.ink50,
    tertiary: AppColors.olive400,
    onTertiary: AppColors.ink900,
    tertiaryContainer: AppColors.olive600,
    onTertiaryContainer: AppColors.ink50,
    error: AppColors.rust500,
    onError: AppColors.ink50,
    errorContainer: AppColors.rust600,
    onErrorContainer: AppColors.ink50,
    // Deep page surface; card sheets sit on parchment-50 (§1.1).
    surface: AppColors.parchment100,
    onSurface: AppColors.ink800,
    surfaceContainerLowest: AppColors.parchment50,
    surfaceContainerLow: AppColors.parchment100,
    surfaceContainer: AppColors.parchment50,
    surfaceContainerHigh: AppColors.parchment200,
    // Sheets/dialogs (web surface-variant role).
    surfaceContainerHighest: AppColors.parchment200,
    onSurfaceVariant: AppColors.ink400,
    outline: AppColors.parchment400,
    outlineVariant: AppColors.parchment300,
    // Material's blue elevation tint would break the warm palette.
    surfaceTint: Colors.transparent,
    inverseSurface: AppColors.parchment900,
    onInverseSurface: AppColors.parchment100,
    inversePrimary: AppColors.oxblood300,
    // scrim = ink-900 @ 72% (§1.1).
    scrim: Color(0xB817110A),
  );

  return ThemeData(
    useMaterial3: true,
    colorScheme: colorScheme,
    textTheme: textTheme,
    // Leather page chrome (#1a130c) with radial glow/grain layered by widgets.
    scaffoldBackgroundColor: AppColors.leather,
    appBarTheme: AppBarThemeData(
      backgroundColor: AppColors.leather,
      foregroundColor: AppColors.ink800,
      elevation: 0,
      scrolledUnderElevation: 0,
      shadowColor: Colors.transparent,
      surfaceTintColor: Colors.transparent,
      centerTitle: true,
      // §1.4: title in the display face at 20 sp, no default elevation.
      titleTextStyle: GoogleFonts.playfairDisplay(
        fontSize: 20,
        height: 1.3,
        fontWeight: FontWeight.w600,
        color: AppColors.ink800,
      ),
    ),
    // Bottom nav shell: leather bg + brass selection (§1.4). The double
    // hairline top border is drawn by the shell widget via BoxDecoration.
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: AppColors.leather,
      elevation: 0,
      shadowColor: Colors.transparent,
      surfaceTintColor: Colors.transparent,
      height: 60,
      indicatorColor: AppColors.brass400,
      labelTextStyle: WidgetStatePropertyAll<TextStyle?>(textTheme.labelSmall),
      iconTheme: WidgetStateProperty.resolveWith<IconThemeData>(
        (Set<WidgetState> states) {
          final bool selected = states.contains(WidgetState.selected);
          return IconThemeData(
            color: selected ? AppColors.brass400 : AppColors.ink400,
            size: 24,
          );
        },
      ),
      labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
    ),
    // Top/in-page tabs: brass indicator over a parchment hairline (§1.4).
    tabBarTheme: TabBarThemeData(
      indicatorColor: AppColors.brass400,
      dividerColor: AppColors.parchment400,
      dividerHeight: 1,
      labelColor: AppColors.ink800,
      unselectedLabelColor: AppColors.ink400,
      labelStyle: textTheme.titleSmall,
      unselectedLabelStyle: textTheme.titleSmall,
    ),
    // Primary CTA (PrimaryButton): oxblood fill, ink label, 48 dp floor,
    // crisp 4 dp corners (§1.3), brass-ring/pressed states owned by the widget.
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: AppColors.oxblood500,
        foregroundColor: AppColors.ink50,
        disabledBackgroundColor: AppColors.parchment300,
        disabledForegroundColor: AppColors.ink400,
        elevation: 0,
        minimumSize: const Size(64, 48),
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.lg,
          vertical: AppSpacing.sm,
        ),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppRadii.sm),
        ),
        textStyle: textTheme.labelLarge,
      ),
    ),
    // Raised secondary action: parchment sheet, hairline-free, elevation 0
    // (warm-black shadows are composed by widgets, never Material's tint).
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: AppColors.parchment200,
        foregroundColor: AppColors.ink800,
        disabledBackgroundColor: AppColors.parchment100,
        disabledForegroundColor: AppColors.ink400,
        elevation: 0,
        shadowColor: Colors.transparent,
        surfaceTintColor: Colors.transparent,
        minimumSize: const Size(64, 48),
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.lg,
          vertical: AppSpacing.sm,
        ),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppRadii.sm),
        ),
        textStyle: textTheme.labelLarge,
      ),
    ),
    // 1 px parchment hairline for standard rules (dashed tickets are drawn
    // by the DashedDivider widget).
    dividerTheme: const DividerThemeData(
      color: AppColors.parchment400,
      thickness: 1,
      space: 1,
    ),
    // Cards = parchment-50 sheet, no Material elevation tint; the signature
    // double-hairline frame + warm-black shadow belong to the AppCard widget.
    cardTheme: CardThemeData(
      color: AppColors.parchment50,
      elevation: 0,
      shadowColor: Colors.transparent,
      surfaceTintColor: Colors.transparent,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(AppRadii.md),
      ),
    ),
  );
}
