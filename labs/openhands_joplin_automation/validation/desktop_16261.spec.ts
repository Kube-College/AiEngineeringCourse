import { test, expect } from './util/test';
import MainScreen from './models/MainScreen';

test.use({ trace: 'on' });

test('cleared tag search closes without associating a suggested tag', async ({ electronApp, mainWindow }, testInfo) => {
	const screen = await new MainScreen(mainWindow).setup();
	const dialog = mainWindow.locator('.prompt-dialog');
	const openTags = async () => {
		const goToAnything = screen.goToAnything;
		await goToAnything.open(electronApp);
		await goToAnything.inputLocator.fill(':setTags');
		await goToAnything.resultLocator('Tags (setTags)').click();
		await expect(dialog).toBeVisible();
		return dialog.locator('.tag-selector input');
	};

	// Create a tag in the disposable profile so the second note has a suggestion.
	await screen.createNewNote('Tag source');
	let input = await openTags();
	await input.fill('existing-tag');
	await input.press('Enter');
	await expect(dialog.getByText('existing-tag', { exact: true })).toBeVisible();
	await dialog.getByRole('button', { name: 'OK' }).click();
	await expect(dialog).toBeHidden();

	await screen.createNewNote('Target without tags');
	input = await openTags();
	await input.fill('existing');
	await expect(dialog.getByText('existing-tag', { exact: true })).toBeVisible();
	for (let i = 0; i < 'existing'.length; i++) await input.press('Backspace');
	await expect(input).toHaveValue('');
	await testInfo.attach('before-enter.png', { body: await mainWindow.screenshot(), contentType: 'image/png' });
	await input.press('Enter');
	await expect(dialog).toBeHidden();

	// Reopen against persisted note state. A selected chip would reveal an association.
	input = await openTags();
	await expect(dialog.locator('.tag-selector [class*="multiValue"]')).toHaveCount(0);
	await testInfo.attach('after-reopen.png', { body: await mainWindow.screenshot(), contentType: 'image/png' });
	await input.press('Escape');
});
