import 'package:flutter/material.dart';

// Your existing project imports
import 'package:demo_ai_even/views/features/voice_enrollment_page.dart';
import 'package:demo_ai_even/views/features/notification/vocabulary_game_page.dart';
import 'package:demo_ai_even/views/features/memory_server.dart';

/// A page that displays a list of available device features.
/// This widget is stateless because it only displays static options and
/// navigates to other pages without managing any internal state.
class FeaturesPage extends StatelessWidget {
  const FeaturesPage({super.key});

  // --- Main Build Method ---
  @override
  Widget build(BuildContext context) {
    // Define the color palette to match the app's aesthetic.
    const primaryColor = Color(0xFF0D1B2A);
    const cardColor = Color(0xFF1B263B);
    const accentColor = Color(0xFF33A1F2);

    return Scaffold(
      backgroundColor: primaryColor,
      appBar: AppBar(
        title: const Text('Features',
            style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
        backgroundColor: primaryColor,
        elevation: 0, // No shadow for a flatter, modern look
      ),
      // Use a ListView for a scrollable and clean list structure.
      body: ListView(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 20),
        children: [
          _buildFeatureTile(
            context: context,
            icon: Icons.image_outlined,
            title: 'Voice Profile',
            subtitle: 'Record your voice for diarization on Memory Page',
            cardColor: cardColor,
            accentColor: accentColor,
            onTap: () {
              Navigator.push(
                context,
                MaterialPageRoute(builder: (context) => const VoiceEnrollmentPage()),
              );
            },
          ),
          _buildFeatureTile(
            context: context,
            icon: Icons.notifications_active_outlined,
            title: 'Vocabulary Game',
            subtitle:
                'Expand your lexicon with real-time feedback in this voice-powered learning game.',
            cardColor: cardColor,
            accentColor: accentColor,
            onTap: () {
              Navigator.push(
                context,
                MaterialPageRoute(
                    builder: (context) => const NotificationPage()),
              );
            },
          ),
          _buildFeatureTile(
            context: context,
            icon: Icons.psychology_alt_outlined,
            title: 'Memory Page',
            subtitle: 'Access transcription + memory command center.',
            cardColor: cardColor,
            accentColor: accentColor,
            onTap: () {
              Navigator.push(
                context,
                MaterialPageRoute(
                    builder: (context) => const MemoryServerPage()),
              );
            },
          ),
        ],
      ),
    );
  }

  // --- UI Builder Methods ---

  /// A reusable helper widget to create consistently styled feature tiles.
  /// This promotes code reuse and ensures a uniform UI.
  Widget _buildFeatureTile({
    required BuildContext context,
    required IconData icon,
    required String title,
    required String subtitle,
    required Color cardColor,
    required Color accentColor,
    required VoidCallback onTap,
  }) {
    return Card(
      color: cardColor,
      elevation: 4,
      margin: const EdgeInsets.only(bottom: 12),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      child: ListTile(
        onTap: onTap,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        contentPadding:
            const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
        leading: Icon(icon, color: accentColor, size: 28),
        title: Text(
          title,
          style: const TextStyle(
            color: Colors.white,
            fontWeight: FontWeight.bold,
            fontSize: 16,
          ),
        ),
        subtitle: Text(
          subtitle,
          style: const TextStyle(color: Colors.white70),
        ),
        trailing: const Icon(Icons.arrow_forward_ios,
            color: Colors.white30, size: 16),
      ),
    );
  }
}
