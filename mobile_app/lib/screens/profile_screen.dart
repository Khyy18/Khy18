import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';
import '../providers/auth_provider.dart';
import '../providers/theme_provider.dart';
import '../theme/app_colors.dart';

class ProfileScreen extends ConsumerStatefulWidget {
  const ProfileScreen({super.key});

  @override
  ConsumerState<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends ConsumerState<ProfileScreen> {
  bool _notifications = true;

  @override
  Widget build(BuildContext context) {
    final isDarkMode = ref.watch(themeProvider) == ThemeMode.dark;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Профиль'),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new, size: 20),
          onPressed: () => context.go('/'),
        ),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          children: [
            const SizedBox(height: 8),
            // Avatar
            Container(
              width: 80,
              height: 80,
              decoration: BoxDecoration(
                gradient: const LinearGradient(
                  colors: [AppColors.primary, AppColors.primaryLight],
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                ),
                borderRadius: BorderRadius.circular(24),
              ),
              child: const Icon(
                Icons.person,
                color: Colors.white,
                size: 40,
              ),
            ),
            const SizedBox(height: 16),
            Text(
              'Главный бухгалтер',
              style: GoogleFonts.spaceGrotesk(
                fontSize: 22,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 4),
            Text(
              'Администратор',
              style: TextStyle(
                color: AppColors.neutral,
                fontSize: 14,
              ),
            ),
            const SizedBox(height: 32),
            // Settings section
            _buildSectionHeader('Настройки'),
            const SizedBox(height: 12),
            _buildSettingsTile(
              icon: Icons.dark_mode_outlined,
              title: 'Тёмная тема',
              trailing: Switch(
                value: isDarkMode,
                onChanged: (v) => ref.read(themeProvider.notifier).toggle(),
                activeColor: AppColors.primary,
              ),
            ),
            const SizedBox(height: 8),
            _buildSettingsTile(
              icon: Icons.notifications_outlined,
              title: 'Уведомления',
              trailing: Switch(
                value: _notifications,
                onChanged: (v) => setState(() => _notifications = v),
                activeColor: AppColors.primary,
              ),
            ),
            const SizedBox(height: 8),
            _buildSettingsTile(
              icon: Icons.lock_outline,
              title: 'PIN-код / Биометрия',
              trailing: const Icon(Icons.chevron_right, color: AppColors.neutral),
              onTap: () => context.go('/pin_setup'),
            ),
            const SizedBox(height: 24),
            // Info section
            _buildSectionHeader('О приложении'),
            const SizedBox(height: 12),
            _buildSettingsTile(
              icon: Icons.info_outline,
              title: 'Версия',
              trailing: Text(
                '1.0.0',
                style: TextStyle(color: AppColors.neutral, fontSize: 14),
              ),
            ),
            const SizedBox(height: 8),
            _buildSettingsTile(
              icon: Icons.description_outlined,
              title: 'Помощник бухгалтера',
              trailing: const SizedBox.shrink(),
            ),
            const SizedBox(height: 32),
            // Logout button
            SizedBox(
              width: double.infinity,
              child: OutlinedButton.icon(
                onPressed: () async {
                  await ref.read(authProvider.notifier).logout();
                  if (context.mounted) {
                    context.go('/login');
                  }
                },
                icon: const Icon(Icons.logout, color: AppColors.expense),
                label: const Text(
                  'Выйти из аккаунта',
                  style: TextStyle(color: AppColors.expense),
                ),
                style: OutlinedButton.styleFrom(
                  side: const BorderSide(color: AppColors.expense),
                  padding: const EdgeInsets.symmetric(vertical: 14),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(14),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSectionHeader(String title) {
    return Align(
      alignment: Alignment.centerLeft,
      child: Text(
        title,
        style: GoogleFonts.spaceGrotesk(
          fontSize: 16,
          fontWeight: FontWeight.w600,
          color: AppColors.neutral,
        ),
      ),
    );
  }

  Widget _buildSettingsTile({
    required IconData icon,
    required String title,
    required Widget trailing,
    VoidCallback? onTap,
  }) {
    return Card(
      child: ListTile(
        contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 4),
        leading: Container(
          width: 40,
          height: 40,
          decoration: BoxDecoration(
            color: AppColors.primary.withOpacity(0.08),
            borderRadius: BorderRadius.circular(12),
          ),
          child: Icon(icon, color: AppColors.primary, size: 20),
        ),
        title: Text(title),
        trailing: trailing,
        onTap: onTap,
      ),
    );
  }
}
