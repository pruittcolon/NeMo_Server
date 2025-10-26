import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

class SettingsPage extends StatefulWidget {
  const SettingsPage({super.key});

  @override
  State<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends State<SettingsPage> {
  int _questionsPerRound = 10;
  bool _soundEnabled = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final prefs = await SharedPreferences.getInstance();
    setState(() {
      _questionsPerRound = prefs.getInt('questionsPerRound') ?? 10;
      _soundEnabled = prefs.getBool('soundEnabled') ?? true;
    });
  }

  Future<void> _save() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setInt('questionsPerRound', _questionsPerRound);
    await prefs.setBool('soundEnabled', _soundEnabled);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text('Sounds Enabled'),
                Switch(
                  value: _soundEnabled,
                  onChanged: (v) => setState(() => _soundEnabled = v),
                ),
              ],
            ),
            const SizedBox(height: 16),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text('Questions per Round'),
                Text('$_questionsPerRound'),
              ],
            ),
            Slider(
              value: _questionsPerRound.toDouble(),
              min: 5,
              max: 30,
              divisions: 5,
              label: '$_questionsPerRound',
              onChanged: (v) => setState(() => _questionsPerRound = v.round()),
            ),
            const Spacer(),
            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                onPressed: () async {
                  await _save();
                  if (mounted) Navigator.of(context).pop();
                },
                child: const Text('Save'),
              ),
            )
          ],
        ),
      ),
    );
  }
}






