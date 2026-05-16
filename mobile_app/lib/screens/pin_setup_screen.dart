import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:google_fonts/google_fonts.dart';

import '../services/secure_storage_service.dart';
import '../theme/app_colors.dart';

class PinSetupScreen extends StatefulWidget {
  final VoidCallback? onComplete;

  const PinSetupScreen({super.key, this.onComplete});

  @override
  State<PinSetupScreen> createState() => _PinSetupScreenState();
}

class _PinSetupScreenState extends State<PinSetupScreen> {
  final SecureStorageService _storageService = SecureStorageService();

  String _pin = '';
  String _confirmPin = '';
  bool _isConfirmStep = false;
  bool _isError = false;

  void _onDigitTap(String digit) {
    HapticFeedback.selectionClick();
    if (_isConfirmStep) {
      if (_confirmPin.length >= 4) return;
      setState(() => _confirmPin += digit);
      if (_confirmPin.length == 4) {
        _validateConfirm();
      }
    } else {
      if (_pin.length >= 4) return;
      setState(() => _pin += digit);
      if (_pin.length == 4) {
        _moveToConfirm();
      }
    }
  }

  void _onBackspace() {
    HapticFeedback.selectionClick();
    if (_isConfirmStep) {
      if (_confirmPin.isEmpty) return;
      setState(() {
        _confirmPin = _confirmPin.substring(0, _confirmPin.length - 1);
      });
    } else {
      if (_pin.isEmpty) return;
      setState(() {
        _pin = _pin.substring(0, _pin.length - 1);
      });
    }
  }

  void _moveToConfirm() {
    Future.delayed(const Duration(milliseconds: 200), () {
      if (mounted) {
        setState(() => _isConfirmStep = true);
      }
    });
  }

  Future<void> _validateConfirm() async {
    if (_pin == _confirmPin) {
      await _storageService.savePin(_pin);
      await _storageService.saveLockEnabled(true);
      await _storageService.saveLastAuthTime(DateTime.now());
      if (mounted) {
        if (widget.onComplete != null) {
          widget.onComplete!();
        } else {
          Navigator.of(context).pop(true);
        }
      }
    } else {
      HapticFeedback.heavyImpact();
      setState(() {
        _isError = true;
        _confirmPin = '';
      });
      await Future.delayed(const Duration(milliseconds: 800));
      if (mounted) {
        setState(() => _isError = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Theme.of(context).scaffoldBackgroundColor,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new_rounded, size: 20),
          onPressed: () => Navigator.of(context).pop(false),
        ),
      ),
      body: SafeArea(
        child: Column(
          children: [
            const Spacer(flex: 1),
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
              child: const Icon(
                Icons.pin_outlined,
                size: 36,
                color: AppColors.primary,
              ),
            ).animate().fadeIn(duration: 400.ms),
            const SizedBox(height: 24),
            Text(
              _isConfirmStep ? 'Повторите PIN-код' : 'Создайте PIN-код',
              style: GoogleFonts.spaceGrotesk(
                fontSize: 22,
                fontWeight: FontWeight.w700,
                color: Theme.of(context).colorScheme.onSurface,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              _isConfirmStep
                  ? 'Введите PIN-код ещё раз'
                  : 'Введите 4 цифры для защиты',
              style: GoogleFonts.manrope(
                fontSize: 14,
                color: Theme.of(context).colorScheme.onSurface.withOpacity(0.6),
              ),
            ),
            if (_isError) ...[
              const SizedBox(height: 12),
              Text(
                'PIN-коды не совпадают',
                style: GoogleFonts.manrope(
                  fontSize: 13,
                  color: AppColors.expense,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ],
            const SizedBox(height: 32),
            _PinDotsSetup(
              length: _isConfirmStep ? _confirmPin.length : _pin.length,
              isError: _isError,
            ),
            const Spacer(flex: 1),
            _PinPadSetup(
              onDigitTap: _onDigitTap,
              onBackspace: _onBackspace,
            ),
            const SizedBox(height: 40),
          ],
        ),
      ),
    );
  }
}

class _PinDotsSetup extends StatelessWidget {
  final int length;
  final bool isError;

  const _PinDotsSetup({required this.length, required this.isError});

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
                      : Theme.of(context).colorScheme.outline,
              width: 1.5,
            ),
          ),
        );
      }),
    ).animate(target: isError ? 1 : 0).shakeX(hz: 4, amount: 6);
  }
}

class _PinPadSetup extends StatelessWidget {
  final void Function(String) onDigitTap;
  final VoidCallback onBackspace;

  const _PinPadSetup({
    required this.onDigitTap,
    required this.onBackspace,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 48),
      child: Column(
        children: [
          _buildRow(context, ['1', '2', '3']),
          const SizedBox(height: 16),
          _buildRow(context, ['4', '5', '6']),
          const SizedBox(height: 16),
          _buildRow(context, ['7', '8', '9']),
          const SizedBox(height: 16),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceEvenly,
            children: [
              const SizedBox(width: 68, height: 68),
              _PinButtonSetup(
                child: Text(
                  '0',
                  style: GoogleFonts.spaceGrotesk(
                    fontSize: 24,
                    fontWeight: FontWeight.w600,
                    color: Theme.of(context).colorScheme.onSurface,
                  ),
                ),
                onTap: () => onDigitTap('0'),
              ),
              _PinButtonSetup(
                child: Icon(
                  Icons.backspace_outlined,
                  color: Theme.of(context).colorScheme.onSurface.withOpacity(0.6),
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

  Widget _buildRow(BuildContext context, List<String> digits) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceEvenly,
      children: digits.map((digit) {
        return _PinButtonSetup(
          child: Text(
            digit,
            style: GoogleFonts.spaceGrotesk(
              fontSize: 24,
              fontWeight: FontWeight.w600,
              color: Theme.of(context).colorScheme.onSurface,
            ),
          ),
          onTap: () => onDigitTap(digit),
        );
      }).toList(),
    );
  }
}

class _PinButtonSetup extends StatelessWidget {
  final Widget child;
  final VoidCallback? onTap;

  const _PinButtonSetup({required this.child, this.onTap});

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
            color: Theme.of(context).colorScheme.outline,
            width: 1,
          ),
        ),
        alignment: Alignment.center,
        child: child,
      ),
    );
  }
}
