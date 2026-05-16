import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:google_fonts/google_fonts.dart';

import '../services/biometric_service.dart';
import '../services/secure_storage_service.dart';
import '../theme/app_colors.dart';

class LockScreen extends StatefulWidget {
  final VoidCallback onUnlocked;

  const LockScreen({super.key, required this.onUnlocked});

  @override
  State<LockScreen> createState() => _LockScreenState();
}

class _LockScreenState extends State<LockScreen> {
  final BiometricService _biometricService = BiometricService();
  final SecureStorageService _storageService = SecureStorageService();

  String _enteredPin = '';
  bool _isError = false;
  bool _biometricAvailable = false;

  @override
  void initState() {
    super.initState();
    _checkBiometric();
  }

  Future<void> _checkBiometric() async {
    final available = await _biometricService.checkAvailability();
    setState(() => _biometricAvailable = available);
    if (available) {
      _tryBiometric();
    }
  }

  Future<void> _tryBiometric() async {
    final success = await _biometricService.authenticate();
    if (success) {
      await _storageService.saveLastAuthTime(DateTime.now());
      widget.onUnlocked();
    }
  }

  Future<void> _onPinComplete() async {
    final savedPin = await _storageService.getPin();
    if (_enteredPin == savedPin) {
      await _storageService.saveLastAuthTime(DateTime.now());
      widget.onUnlocked();
    } else {
      HapticFeedback.heavyImpact();
      setState(() {
        _isError = true;
        _enteredPin = '';
      });
      await Future.delayed(const Duration(milliseconds: 800));
      if (mounted) {
        setState(() => _isError = false);
      }
    }
  }

  void _onDigitTap(String digit) {
    if (_enteredPin.length >= 4) return;
    HapticFeedback.selectionClick();
    setState(() {
      _enteredPin += digit;
    });
    if (_enteredPin.length == 4) {
      _onPinComplete();
    }
  }

  void _onBackspace() {
    if (_enteredPin.isEmpty) return;
    HapticFeedback.selectionClick();
    setState(() {
      _enteredPin = _enteredPin.substring(0, _enteredPin.length - 1);
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.backgroundLight,
      body: SafeArea(
        child: Column(
          children: [
            const Spacer(flex: 2),
            // Lock icon
            Container(
              width: 72,
              height: 72,
              decoration: BoxDecoration(
                color: AppColors.primary.withOpacity(0.08),
                borderRadius: BorderRadius.circular(20),
                border: Border.all(
                  color: AppColors.primary.withOpacity(0.15),
                  width: 1,
                ),
              ),
              child: Icon(
                _biometricAvailable
                    ? Icons.fingerprint_rounded
                    : Icons.lock_outline_rounded,
                size: 36,
                color: AppColors.primary,
              ),
            ).animate().fadeIn(duration: 400.ms).scale(
                  begin: const Offset(0.8, 0.8),
                  end: const Offset(1, 1),
                ),
            const SizedBox(height: 24),
            Text(
              'Введите PIN-код',
              style: GoogleFonts.spaceGrotesk(
                fontSize: 22,
                fontWeight: FontWeight.w700,
                color: AppColors.textPrimaryLight,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              'Для доступа к приложению',
              style: GoogleFonts.manrope(
                fontSize: 14,
                color: AppColors.textSecondaryLight,
              ),
            ),
            const SizedBox(height: 32),
            // PIN dots
            _PinDots(
              length: _enteredPin.length,
              isError: _isError,
            ),
            const Spacer(flex: 1),
            // PIN pad
            _PinPad(
              onDigitTap: _onDigitTap,
              onBackspace: _onBackspace,
              onBiometric: _biometricAvailable ? _tryBiometric : null,
            ),
            const SizedBox(height: 40),
          ],
        ),
      ),
    );
  }
}

class _PinDots extends StatelessWidget {
  final int length;
  final bool isError;

  const _PinDots({required this.length, required this.isError});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: List.generate(4, (index) {
        final filled = index < length;
        return Container(
          margin: const EdgeInsets.symmetric(horizontal: 8),
          width: 14,
          height: 14,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: isError
                ? AppColors.expense
                : filled
                    ? AppColors.primary
                    : Colors.transparent,
            border: Border.all(
              color: isError
                  ? AppColors.expense
                  : filled
                      ? AppColors.primary
                      : AppColors.borderLight,
              width: 1.5,
            ),
          ),
        );
      }),
    ).animate(target: isError ? 1 : 0).shakeX(hz: 4, amount: 6);
  }
}

class _PinPad extends StatelessWidget {
  final void Function(String) onDigitTap;
  final VoidCallback onBackspace;
  final VoidCallback? onBiometric;

  const _PinPad({
    required this.onDigitTap,
    required this.onBackspace,
    this.onBiometric,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 48),
      child: Column(
        children: [
          _buildRow(['1', '2', '3']),
          const SizedBox(height: 16),
          _buildRow(['4', '5', '6']),
          const SizedBox(height: 16),
          _buildRow(['7', '8', '9']),
          const SizedBox(height: 16),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceEvenly,
            children: [
              _PinButton(
                child: onBiometric != null
                    ? Icon(
                        Icons.fingerprint_rounded,
                        color: AppColors.primary,
                        size: 28,
                      )
                    : const SizedBox.shrink(),
                onTap: onBiometric,
              ),
              _PinButton(
                child: Text(
                  '0',
                  style: GoogleFonts.spaceGrotesk(
                    fontSize: 24,
                    fontWeight: FontWeight.w600,
                    color: AppColors.textPrimaryLight,
                  ),
                ),
                onTap: () => onDigitTap('0'),
              ),
              _PinButton(
                child: Icon(
                  Icons.backspace_outlined,
                  color: AppColors.textSecondaryLight,
                  size: 24,
                ),
                onTap: onBackspace,
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildRow(List<String> digits) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceEvenly,
      children: digits.map((digit) {
        return _PinButton(
          child: Text(
            digit,
            style: GoogleFonts.spaceGrotesk(
              fontSize: 24,
              fontWeight: FontWeight.w600,
              color: AppColors.textPrimaryLight,
            ),
          ),
          onTap: () => onDigitTap(digit),
        );
      }).toList(),
    );
  }
}

class _PinButton extends StatelessWidget {
  final Widget child;
  final VoidCallback? onTap;

  const _PinButton({required this.child, this.onTap});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: 68,
        height: 68,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: Colors.transparent,
          border: Border.all(
            color: AppColors.borderLight,
            width: 1,
          ),
        ),
        alignment: Alignment.center,
        child: child,
      ),
    );
  }
}
