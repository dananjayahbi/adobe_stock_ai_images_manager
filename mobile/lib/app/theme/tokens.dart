import 'package:flutter/material.dart';

/// Design tokens ported verbatim from frontend-new/tailwind.config.ts.
abstract final class AppColors {
  // parchment (surfaces)
  static const parchment50 = Color(0xFF2b2119);
  static const parchment100 = Color(0xFF201812);
  static const parchment200 = Color(0xFF362a20);
  static const parchment300 = Color(0xFF423427);
  static const parchment400 = Color(0xFF4f3f2e);
  static const parchment500 = Color(0xFF6b563e);
  static const parchment600 = Color(0xFF8a7050);
  static const parchment700 = Color(0xFFa58a64);
  static const parchment800 = Color(0xFFc0a57c);
  static const parchment900 = Color(0xFFd8c39a);
  // ink (type on dark)
  static const ink50 = Color(0xFFf7efdd);
  static const ink200 = Color(0xFFd8c9ae);
  static const ink400 = Color(0xFFa29175);
  static const ink600 = Color(0xFFc9b993);
  static const ink800 = Color(0xFFeee3cc);
  static const ink900 = Color(0xFF17110a);
  // brass (accents)
  static const brass300 = Color(0xFFddc284);
  static const brass400 = Color(0xFFcba857);
  static const brass500 = Color(0xFFa98541);
  static const brass600 = Color(0xFF8a6a2f);
  static const brass700 = Color(0xFF6b5123);
  // oxblood (primary actions)
  static const oxblood300 = Color(0xFFe09a8f);
  static const oxblood400 = Color(0xFFd2796a);
  static const oxblood500 = Color(0xFF8b3a2f);
  static const oxblood600 = Color(0xFF742f26);
  static const oxblood700 = Color(0xFF5c251e);
  // olive (success) / rust (warning-failure)
  static const olive400 = Color(0xFF9db066);
  static const olive500 = Color(0xFF5b6334);
  static const olive600 = Color(0xFF4a5129);
  static const rust400 = Color(0xFFdd9d5c);
  static const rust500 = Color(0xFFa15f26);
  static const rust600 = Color(0xFF824a1c);

  /// Leather page background (web globals.css).
  static const leather = Color(0xFF1a130c);
}

abstract final class AppSpacing {
  static const double xs = 4, sm = 8, md = 12, lg = 16, xl = 24, xxl = 32;
}

abstract final class AppRadii {
  static const double sm = 4, md = 8;
}
