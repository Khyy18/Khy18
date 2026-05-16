import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';
import '../theme/app_colors.dart';

class CalculationsScreen extends StatelessWidget {
  const CalculationsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, result) {
        if (!didPop) context.go('/');
      },
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Расчёты'),
          leading: IconButton(
            icon: const Icon(Icons.arrow_back_ios_new, size: 20),
            onPressed: () => context.go('/'),
          ),
        ),
        body: SafeArea(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Калькуляторы',
                  style: GoogleFonts.spaceGrotesk(
                    fontSize: 22,
                    fontWeight: FontWeight.w700,
                    letterSpacing: -0.5,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  'Выберите тип расчёта',
                  style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                        color: AppColors.neutral,
                      ),
                ),
                const SizedBox(height: 24),
                _HubCard(
                  icon: Icons.calculate_outlined,
                  title: 'Зарплата',
                  subtitle: 'Расчёт заработной платы с учётом ставки и стажа',
                  onTap: () => context.go('/salary'),
                  delay: 0,
                ),
                const SizedBox(height: 12),
                _HubCard(
                  icon: Icons.beach_access_outlined,
                  title: 'Отпускные',
                  subtitle: 'Расчёт отпускных выплат',
                  onTap: () => context.go('/vacation'),
                  delay: 100,
                ),
                const SizedBox(height: 12),
                _HubCard(
                  icon: Icons.local_hospital_outlined,
                  title: 'Больничный',
                  subtitle: 'Расчёт больничного листа',
                  onTap: () => context.go('/sick'),
                  delay: 200,
                ),
                const SizedBox(height: 12),
                _HubCard(
                  icon: Icons.exit_to_app_outlined,
                  title: 'Компенсация при увольнении',
                  subtitle: 'Расчёт компенсации за неиспользованный отпуск',
                  onTap: () => context.go('/compensation'),
                  delay: 300,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _HubCard extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;
  final int delay;

  const _HubCard({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
    this.delay = 0,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: const BorderSide(color: AppColors.borderLight, width: 1),
      ),
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: () {
          HapticFeedback.selectionClick();
          onTap();
        },
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Row(
            children: [
              Container(
                width: 48,
                height: 48,
                decoration: BoxDecoration(
                  color: AppColors.primary.withOpacity(0.1),
                  borderRadius: BorderRadius.circular(14),
                ),
                child: Icon(icon, color: AppColors.primary, size: 24),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: GoogleFonts.spaceGrotesk(
                        fontSize: 16,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      subtitle,
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                            color: AppColors.neutral,
                          ),
                    ),
                  ],
                ),
              ),
              const Icon(
                Icons.arrow_forward_ios,
                size: 16,
                color: AppColors.neutral,
              ),
            ],
          ),
        ),
      ),
    )
        .animate()
        .fadeIn(delay: Duration(milliseconds: delay), duration: 300.ms)
        .slideX(begin: 0.05, end: 0);
  }
}
