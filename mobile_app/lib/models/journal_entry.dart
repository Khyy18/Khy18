class JournalEntry {
  final int? id;
  final String type; // 'income' | 'expense'
  final double amount;
  final String description;
  final String date;
  final int? chatId;

  JournalEntry({
    this.id,
    required this.type,
    required this.amount,
    required this.description,
    required this.date,
    this.chatId,
  });

  factory JournalEntry.fromJson(Map<String, dynamic> json) {
    return JournalEntry(
      id: json['id'] as int?,
      type: json['type'] as String? ?? 'income',
      amount: (json['amount'] as num?)?.toDouble() ?? 0,
      description: json['description'] as String? ?? '',
      date: json['date'] as String? ?? '',
      chatId: json['chat_id'] as int?,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      if (id != null) 'id': id,
      'type': type,
      'amount': amount,
      'description': description,
      'date': date,
      if (chatId != null) 'chat_id': chatId,
    };
  }
}
