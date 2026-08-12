<?php

namespace Tests\Unit;

use Tests\TestCase;

class Providers_model_Test extends TestCase
{
    public function testProviderModelOperations(): void
    {
        $CI =& get_instance();

        $CI->load->model('providers_model');

        $providers = $CI->providers_model->get();

        $this->assertNotEmpty($providers);

        foreach ($providers as $provider) {
            $this->assertNotEmpty($provider['name']);
            $this->assertEquals($provider['name'], $provider['first_name']);
            $this->assertEquals('', $provider['last_name']);
            $this->assertArrayHasKey('services', $provider);
            $this->assertArrayHasKey('settings', $provider);
            $this->assertNotEmpty($provider['settings']['working_plan']);
            $this->assertNotEmpty($provider['timezone']);
        }

        $provider = $CI->providers_model->find(2);

        $this->assertEquals('Ярослава Полещук', $provider['name']);
        $this->assertContains(1, $provider['services']);

        $available_providers = $CI->providers_model->get_available_providers();

        $this->assertNotEmpty($available_providers);

        $results = $CI->providers_model->search('Полещук');

        $this->assertNotEmpty($results);

        $options = $CI->providers_model->to_options();

        $this->assertNotEmpty($options);
        $this->assertArrayHasKey('value', $options[0]);
        $this->assertArrayHasKey('label', $options[0]);
    }

    public function testProviderSaveUpdateDelete(): void
    {
        $CI =& get_instance();

        $CI->load->model('providers_model');

        $provider_id = $CI->providers_model->save([
            'name' => 'TEST EXECUTOR',
            'services' => [1],
        ]);

        $this->assertNotEmpty($provider_id);

        $provider = $CI->providers_model->find($provider_id);

        $this->assertEquals('TEST EXECUTOR', $provider['name']);
        $this->assertEquals([1], $provider['services']);

        $CI->providers_model->save([
            'id' => $provider_id,
            'name' => 'TEST EXECUTOR 2',
            'services' => [2],
        ]);

        $provider = $CI->providers_model->find($provider_id);

        $this->assertEquals('TEST EXECUTOR 2', $provider['name']);
        $this->assertEquals([2], $provider['services']);

        $CI->providers_model->delete($provider_id);

        $this->expectException(\InvalidArgumentException::class);

        $CI->providers_model->find($provider_id);
    }
}