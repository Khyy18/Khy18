class Reminder {
  final int? id;
  final String title;
  final String deadline;
  final String description;
  final bool enabled;
  final int? chatId;

  Reminder({
    this.id,
    required this.title,
    required this.deadline,
    required this.description,
    required this.enabled,
    this.chatId,
  });

  factory Reminder.fromJson(Map<String, dynamic> json) {
    return Reminder(
      id: json['id'] as int?,
      title: json['title'] as String? ?? '',
      deadline: json['deadline'] as String? ?? '',
      description: json['description'] as String? ?? '',
      enabled: json['enabled'] as bool? ?? true,
      chatId: json['chat_id'] as int?,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      if (id != null) 'id': id,
      'title': title,
      'deadline': deadline,
      'description': description,
      'enabled': enabled,
      if (chatId != null) 'chat_id': chatId,
    };
  }
}
