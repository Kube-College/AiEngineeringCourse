import { test, expect } from './util/test';
import MainScreen from './models/MainScreen';
import setSettingValue from './util/setSettingValue';

test.use({ trace: 'on' });

for (const item of [
	{ name: 'note', setting: 'newNoteFocus', button: '.new-note-button', placeholder: 'Creating new note...' },
	{ name: 'to-do', setting: 'newTodoFocus', button: '.new-todo-button', placeholder: 'Creating new to-do...' },
]) {
	test(`new ${item.name} accepts typing in the configured title field`, async ({ electronApp, mainWindow }, testInfo) => {
		const screen = await new MainScreen(mainWindow).setup();
		await setSettingValue(electronApp, mainWindow, item.setting, 'title');
		await mainWindow.locator(item.button).click();
		const title = screen.noteEditor.noteTitleInput;
		await expect(title).toHaveAttribute('placeholder', item.placeholder);
		await testInfo.attach('after-create.png', { body: await mainWindow.screenshot(), contentType: 'image/png' });
		await mainWindow.keyboard.type(`Focus check ${item.name}`);
		await expect(title).toHaveValue(`Focus check ${item.name}`);
	});
}
