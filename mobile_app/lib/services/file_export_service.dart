import 'dart:io';
import 'dart:typed_data';

import 'package:open_file/open_file.dart';
import 'package:path_provider/path_provider.dart';

/// Saves bytes to a temporary file and opens it for viewing/sharing.
/// Returns the file path where the file was saved.
Future<String> saveAndOpenFile(List<int> bytes, String filename) async {
  final dir = await getTemporaryDirectory();
  final filePath = '${dir.path}/$filename';
  final file = File(filePath);
  await file.writeAsBytes(Uint8List.fromList(bytes));
  await OpenFile.open(filePath);
  return filePath;
}
