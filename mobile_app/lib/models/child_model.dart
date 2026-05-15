class ChildModel {
  final int? id;
  final String name;
  final String group;
  final String parentName;
  final double monthlyFee;
  final int? chatId;

  ChildModel({
    this.id,
    required this.name,
    required this.group,
    required this.parentName,
    required this.monthlyFee,
    this.chatId,
  });

  factory ChildModel.fromJson(Map<String, dynamic> json) {
    return ChildModel(
      id: json['id'] as int?,
      name: json['name'] as String? ?? '',
      group: json['group_name'] as String? ?? '',
      parentName: json['parent_name'] as String? ?? '',
      monthlyFee: (json['monthly_fee'] as num?)?.toDouble() ?? 0,
      chatId: json['chat_id'] as int?,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      if (id != null) 'id': id,
      'name': name,
      'group_name': group,
      'parent_name': parentName,
      'monthly_fee': monthlyFee,
      if (chatId != null) 'chat_id': chatId,
    };
  }
}
