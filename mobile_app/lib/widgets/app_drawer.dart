import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../theme/app_colors.dart';

class AppDrawer extends StatelessWidget {
  final void Function(String route) onNavigate;

  const AppDrawer({super.key, required this.onNavigate});

  @override
  Widget build(BuildContext context) {
    return Drawer(
      child: Column(
        children: [
          Container(
            width: double.infinity,
            padding: const EdgeInsets.fromLTRB(24, 60, 24, 24),
            decoration: const BoxDecoration(
              gradient: LinearGradient(
                colors: [AppColors.primary, AppColors.primaryDark],
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
              ),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(
                  width: 56,
                  height: 56,
                  decoration: BoxDecoration(
                    color: Colors.white.withOpacity(0.2),
                    borderRadius: BorderRadius.circular(16),
                  ),
                  child: const Icon(
                    Icons.account_balance,
                    color: Colors.white,
                    size: 28,
                  ),
                ),
                const SizedBox(height: 16),
                Text(
                  'Детский сад',
                  style: GoogleFonts.spaceGrotesk(
                    fontSize: 22,
                    fontWeight: FontWeight.w700,
                    color: Colors.white,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  'Бухгалтерия',
                  style: GoogleFonts.manrope(
                    fontSize: 14,
                    color: Colors.white.withOpacity(0.7),
                  ),
                ),
              ],
            ),
          ),
          Expanded(
            child: ListView(
              padding: const EdgeInsets.symmetric(vertical: 8),
              children: [
                _DrawerItem(
                  icon: Icons.dashboard_outlined,
                  label: 'Главная',
                  onTap: () => onNavigate('/'),
                ),
                _DrawerItem(
                  icon: Icons.calculate_outlined,
                  label: 'Зарплата',
                  onTap: () => onNavigate('/salary'),
                ),
                _DrawerItem(
                  icon: Icons.beach_access_outlined,
                  label: 'Отпускные',
                  onTap: () => onNavigate('/vacation'),
                ),
                _DrawerItem(
                  icon: Icons.local_hospital_outlined,
                  label: 'Больничный',
                  onTap: () => onNavigate('/sick'),
                ),
                _DrawerItem(
                  icon: Icons.calendar_month_outlined,
                  label: 'Табель',
                  onTap: () => onNavigate('/timesheet'),
                ),
                _DrawerItem(
                  icon: Icons.child_care_outlined,
                  label: 'Дети',
                  onTap: () => onNavigate('/children'),
                ),
                _DrawerItem(
                  icon: Icons.book_outlined,
                  label: 'Журнал',
                  onTap: () => onNavigate('/journal'),
                ),
                _DrawerItem(
                  icon: Icons.search,
                  label: 'КБК',
                  onTap: () => onNavigate('/kbk'),
                ),
                _DrawerItem(
                  icon: Icons.notifications_outlined,
                  label: 'Напоминания',
                  onTap: () => onNavigate('/reminders'),
                ),
                _DrawerItem(
                  icon: Icons.payment_outlined,
                  label: 'Платёжки',
                  onTap: () => onNavigate('/payment'),
                ),
                const Divider(indent: 16, endIndent: 16),
                _DrawerItem(
                  icon: Icons.auto_awesome,
                  label: 'AI Ассистент',
                  onTap: () => onNavigate('/ai_chat'),
                  accent: true,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _DrawerItem extends StatelessWidget {
  final IconData icon;
  final String label;
  final VoidCallback onTap;
  final bool accent;

  const _DrawerItem({
    required this.icon,
    required this.label,
    required this.onTap,
    this.accent = false,
  });

  @override
  Widget build(BuildContext context) {
    return ListTile(
      leading: Icon(
        icon,
        color: accent ? AppColors.primary : null,
        size: 22,
      ),
      title: Text(
        label,
        style: TextStyle(
          fontWeight: accent ? FontWeight.w600 : FontWeight.w500,
          color: accent ? AppColors.primary : null,
        ),
      ),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      contentPadding: const EdgeInsets.symmetric(horizontal: 24),
      onTap: () {
        Navigator.pop(context);
        onTap();
      },
    );
  }
}
